"""Decision authoring over an authoritative, conflict-checked project source."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

from pydantic import ValidationError

from deykit.application.authoring_views import (
    EditorEditV1,
    EditorTransformV1,
    transform_editor,
)
from deykit.application.errors import ServiceFailure
from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.identities import new_id, validate_resource_id
from deykit.contracts.json_value import (
    JsonDocument,
    JsonError,
    JsonValue,
    bytes_hash,
    parse_json,
    semantic_hash,
)
from deykit.contracts.ports import (
    Clock,
    Collection,
    ProjectSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import (
    ChoiceDefinition,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    LabelRecord,
    RegressionRecord,
)
from deykit.contracts.schema import compile_schema
from deykit.domain.definitions import definition_hash, missing_options, select_input

R = TypeVar("R", bound=Record)


@dataclass(frozen=True)
class Versioned(Generic[R]):
    record: R
    etag: str


@dataclass(frozen=True)
class DecisionView:
    decision: Versioned[DecisionRecord]
    draft: Versioned[DecisionDraft]


@dataclass(frozen=True)
class DecisionPage:
    items: tuple[DecisionView, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class RevisionPage:
    items: tuple[Versioned[DecisionRevision], ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class LatestSavedDefinition:
    """Explicit immutable saved context; authoring defaults to the current draft."""

    decision: Versioned[DecisionRecord]
    revision: Versioned[DecisionRevision]


@dataclass(frozen=True)
class IncompatibleReference:
    kind: str
    resource_id: str
    decision_id: str
    dataset_id: str
    case_id: str
    question_id: str
    missing_option_ids: tuple[str, ...]


@dataclass(frozen=True)
class DefinitionDiff:
    before_hash: str
    after_hash: str
    input_changed: bool
    question_changed: bool
    option_order_changed: bool
    added_option_ids: tuple[str, ...]
    removed_option_ids: tuple[str, ...]
    changed_option_ids: tuple[str, ...]
    incompatible_references: tuple[IncompatibleReference, ...]


@dataclass(frozen=True)
class DraftTransformReviewV1:
    """A proposed exact-source edit and its captured, read-only reference impact."""

    transform: EditorTransformV1
    incompatible_references: tuple[IncompatibleReference, ...] | None


def _failure(
    code: ErrorCode, resource_id: str | None = None, reason: str | None = None
) -> ServiceFailure:
    # ServiceError validates safe, portable identifiers and fixed public messages.
    return ServiceFailure(ServiceError(code=code, resource_id=resource_id, reason=reason))


def _valid_id(value: str) -> str:
    try:
        return validate_resource_id(value)
    except ValueError:
        raise _failure("validation_error", reason="invalid_resource_id") from None


def _key(collection: str, resource_id: str, scope: tuple[str, ...] = ()) -> ResourceKey:
    return ResourceKey(cast(Collection, collection), _valid_id(resource_id), scope)


def _intent(command: str, *values: str | None) -> str:
    try:
        digests = [
            bytes_hash(value.encode("utf-8")) if value is not None else None for value in values
        ]
        return semantic_hash({"command": command, "values": cast(JsonValue, digests)})
    except (AttributeError, UnicodeEncodeError):
        raise _failure("validation_error", reason="invalid_request_value") from None


def _decoded(record_type: type[R], stored: StoredRecord) -> R:
    try:
        return load_record(record_type, stored.body)
    except JsonError as error:
        raise _failure("validation_error", stored.key.resource_id, error.code) from None


def revision_editor_source(revision: DecisionRevision) -> str:
    """Return the canonical editable source for an admitted saved revision."""
    return dump_record(revision.definition).decode("utf-8")


def _required(source: ProjectSource, record_type: type[R], key: ResourceKey) -> tuple[R, str]:
    stored = source.read(key)
    if stored is None:
        raise _failure("not_found", key.resource_id)
    return _decoded(record_type, stored), stored.etag


def _page(
    ids: tuple[str, ...], cursor: str | None, limit: int
) -> tuple[tuple[str, ...], str | None]:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise _failure("validation_error", reason="invalid_page_limit")
    if cursor is not None:
        _valid_id(cursor)
    ordered = tuple(sorted(ids))
    remaining = tuple(item for item in ordered if cursor is None or item > cursor)
    chosen = remaining[:limit]
    next_cursor = chosen[-1] if len(remaining) > limit else None
    return chosen, next_cursor


class DecisionService:
    """Only the ProjectSource protocol crosses the persistence boundary."""

    def __init__(
        self, source: ProjectSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source = source
        self.clock = clock
        self.id_factory = id_factory

    def create(
        self, decision_id: str, name: str, editor_source: str, *, operation_id: str
    ) -> DecisionView:
        decision_id = _valid_id(decision_id)
        _valid_id(operation_id)
        intent = _intent("decision.create", decision_id, name, editor_source)
        replay = self.source.operation_receipt(operation_id, intent_hash=intent)
        if replay is not None:
            return self._view_from_receipt(decision_id, replay.changes)
        try:
            decision = DecisionRecord(id=decision_id, name=name)
            draft = DecisionDraft(
                decision_id=decision_id,
                editor_source=editor_source,
                updated_at=self.clock.utc_now(),
            )
            changes = (
                SourceChange(_key("decisions", decision_id), dump_record(decision), None),
                SourceChange(_key("drafts", decision_id), dump_record(draft), None),
            )
        except (ValidationError, JsonError):
            raise _failure("validation_error", decision_id, "invalid_decision") from None
        receipt = self.source.commit(operation_id, changes, intent_hash=intent)
        return self._view_from_receipt(decision_id, receipt.changes)

    def read(self, decision_id: str) -> DecisionView:
        decision_id = _valid_id(decision_id)
        with self.source.consistent_read() as source:
            return self._read_view(source, decision_id)

    def list(
        self, *, include_archived: bool = False, cursor: str | None = None, limit: int = 50
    ) -> DecisionPage:
        with self.source.consistent_read() as source:
            ids = source.list_ids("decisions")
            visible: list[str] = []
            for decision_id in ids:
                decision, _ = _required(source, DecisionRecord, _key("decisions", decision_id))
                if include_archived or not decision.archived:
                    visible.append(decision_id)
            chosen, next_cursor = _page(tuple(visible), cursor, limit)
            items = tuple(self._read_view(source, item) for item in chosen)
        return DecisionPage(items, len(visible), next_cursor)

    def update_draft(
        self, decision_id: str, editor_source: str, *, expected_etag: str, operation_id: str
    ) -> Versioned[DecisionDraft]:
        decision_id = _valid_id(decision_id)
        _valid_id(operation_id)
        intent = _intent("decision.update_draft", decision_id, editor_source, expected_etag)
        replay = self.source.operation_receipt(operation_id, intent_hash=intent)
        if replay is not None:
            stored = replay.changes[0]
            return Versioned(_decoded(DecisionDraft, stored), stored.etag)
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                stored = replay.changes[0]
                return Versioned(_decoded(DecisionDraft, stored), stored.etag)
            decision, _ = _required(source, DecisionRecord, _key("decisions", decision_id))
            draft, _ = _required(source, DecisionDraft, _key("drafts", decision_id))
            if decision.archived:
                raise _failure("conflict", decision_id, "decision_archived")
            try:
                changed = DecisionDraft(
                    decision_id=decision_id,
                    editor_source=editor_source,
                    updated_at=self.clock.utc_now(),
                    base_revision_id=draft.base_revision_id,
                )
                body = dump_record(changed)
            except (ValidationError, JsonError):
                raise _failure("validation_error", decision_id, "invalid_draft") from None
            receipt = source.commit(
                operation_id,
                (SourceChange(_key("drafts", decision_id), body, expected_etag),),
                intent_hash=intent,
            )
        stored = receipt.changes[0]
        return Versioned(_decoded(DecisionDraft, stored), stored.etag)

    def validate(self, decision_id: str) -> ChoiceDefinition:
        view = self.read(decision_id)
        draft = view.draft.record
        return self._definition(draft.editor_source, decision_id)

    def select_case(self, decision_id: str, input_source: str) -> JsonDocument:
        definition = self.validate(decision_id)
        try:
            return select_input(definition, JsonDocument(input_source))
        except JsonError as error:
            raise _failure("validation_error", decision_id, error.code) from None

    def save(
        self,
        decision_id: str,
        *,
        expected_draft_etag: str,
        expected_decision_etag: str,
        operation_id: str,
        note: str = "",
    ) -> Versioned[DecisionRevision]:
        decision_id = _valid_id(decision_id)
        _valid_id(operation_id)
        intent = _intent(
            "decision.save", decision_id, expected_draft_etag, expected_decision_etag, note
        )
        replay = self.source.operation_receipt(operation_id, intent_hash=intent)
        if replay is not None:
            stored = next(item for item in replay.changes if item.key.collection == "revisions")
            return Versioned(_decoded(DecisionRevision, stored), stored.etag)
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                stored = next(item for item in replay.changes if item.key.collection == "revisions")
                return Versioned(_decoded(DecisionRevision, stored), stored.etag)
            decision, _ = _required(source, DecisionRecord, _key("decisions", decision_id))
            draft, _ = _required(source, DecisionDraft, _key("drafts", decision_id))
            if decision.archived:
                raise _failure("conflict", decision_id, "decision_archived")
            definition = self._definition(draft.editor_source, decision_id)
            revision_id = _valid_id(self.id_factory())
            try:
                revision = DecisionRevision(
                    id=revision_id,
                    decision_id=decision_id,
                    definition=definition,
                    content_hash=definition_hash(definition),
                    created_at=self.clock.utc_now(),
                    note=note,
                )
                pointer = DecisionRecord(
                    id=decision.id,
                    name=decision.name,
                    archived=decision.archived,
                    latest_revision_id=revision_id,
                )
                updated_draft = DecisionDraft(
                    decision_id=decision_id,
                    editor_source=draft.editor_source,
                    updated_at=draft.updated_at,
                    base_revision_id=revision_id,
                )
                changes = (
                    SourceChange(
                        _key("revisions", revision_id, (decision_id,)), dump_record(revision), None
                    ),
                    SourceChange(
                        _key("decisions", decision_id), dump_record(pointer), expected_decision_etag
                    ),
                    SourceChange(
                        _key("drafts", decision_id), dump_record(updated_draft), expected_draft_etag
                    ),
                )
            except (ValidationError, JsonError):
                raise _failure("validation_error", decision_id, "invalid_revision") from None
            receipt = source.commit(operation_id, changes, intent_hash=intent)
        stored = next(item for item in receipt.changes if item.key.collection == "revisions")
        return Versioned(_decoded(DecisionRevision, stored), stored.etag)

    def revision(self, decision_id: str, revision_id: str) -> Versioned[DecisionRevision]:
        key = _key("revisions", revision_id, (_valid_id(decision_id),))
        with self.source.consistent_read() as source:
            record, etag = _required(source, DecisionRevision, key)
        if record.decision_id != decision_id or record.id != revision_id:
            raise _failure("validation_error", revision_id, "revision_identity_mismatch")
        if definition_hash(record.definition) != record.content_hash:
            raise _failure("validation_error", revision_id, "revision_hash_mismatch")
        return Versioned(record, etag)

    def latest_saved_revision(self, decision_id: str) -> LatestSavedDefinition:
        """Capture the latest saved revision explicitly at one source boundary."""
        decision_id = _valid_id(decision_id)
        with self.source.consistent_read() as source:
            decision, etag = _required(source, DecisionRecord, _key("decisions", decision_id))
            if decision.archived:
                raise _failure("conflict", decision_id, "decision_archived")
            if decision.latest_revision_id is None:
                raise _failure("validation_error", decision_id, "unsaved_decision")
            revision = self._versioned_revision(source, decision_id, decision.latest_revision_id)
            return LatestSavedDefinition(Versioned(decision, etag), revision)

    def history(
        self, decision_id: str, *, cursor: str | None = None, limit: int = 50
    ) -> RevisionPage:
        decision_id = _valid_id(decision_id)
        with self.source.consistent_read() as source:
            _required(source, DecisionRecord, _key("decisions", decision_id))
            ids = source.list_ids("revisions", (decision_id,))
            chosen, next_cursor = _page(ids, cursor, limit)
            items = tuple(
                self._versioned_revision(source, decision_id, revision_id) for revision_id in chosen
            )
        return RevisionPage(items, len(ids), next_cursor)

    def diff(self, decision_id: str, before: str, after: str) -> DefinitionDiff:
        with self.source.consistent_read():
            previous = self._resolve_definition(decision_id, before)
            current = self._resolve_definition(decision_id, after)
            old_question, new_question = previous.questions[0], current.questions[0]
            old_options = {option.id: option for option in old_question.options}
            new_options = {option.id: option for option in new_question.options}
            removed = tuple(
                option.id for option in old_question.options if option.id not in new_options
            )
            added = tuple(
                option.id for option in new_question.options if option.id not in old_options
            )
            changed = tuple(
                option.id
                for option in new_question.options
                if option.id in old_options and option != old_options[option.id]
            )
            return DefinitionDiff(
                before_hash=definition_hash(previous),
                after_hash=definition_hash(current),
                input_changed=(
                    previous.input_kind,
                    JsonDocument(previous.input_schema_source).content_hash
                    if previous.input_schema_source is not None
                    else None,
                    previous.selected_fields,
                )
                != (
                    current.input_kind,
                    JsonDocument(current.input_schema_source).content_hash
                    if current.input_schema_source is not None
                    else None,
                    current.selected_fields,
                ),
                question_changed=(old_question.id, old_question.instructions)
                != (new_question.id, new_question.instructions),
                option_order_changed=(
                    tuple(option_id for option_id in old_options if option_id in new_options)
                    != tuple(option_id for option_id in new_options if option_id in old_options)
                ),
                added_option_ids=added,
                removed_option_ids=removed,
                changed_option_ids=changed,
                incompatible_references=self._incompatible_references(decision_id, current),
            )

    def rename(
        self, decision_id: str, name: str, *, expected_etag: str, operation_id: str
    ) -> Versioned[DecisionRecord]:
        return self._change_decision(decision_id, expected_etag, operation_id, name=name)

    def archive(
        self, decision_id: str, *, expected_etag: str, operation_id: str
    ) -> Versioned[DecisionRecord]:
        return self._change_decision(decision_id, expected_etag, operation_id, archived=True)

    def restore(
        self, decision_id: str, *, expected_etag: str, operation_id: str
    ) -> Versioned[DecisionRecord]:
        return self._change_decision(decision_id, expected_etag, operation_id, archived=False)

    def restore_revision_to_draft(
        self,
        decision_id: str,
        revision_id: str,
        *,
        expected_draft_etag: str,
        operation_id: str,
    ) -> Versioned[DecisionDraft]:
        decision_id = _valid_id(decision_id)
        _valid_id(operation_id)
        intent = _intent("decision.restore_revision", decision_id, revision_id, expected_draft_etag)
        replay = self.source.operation_receipt(operation_id, intent_hash=intent)
        if replay is not None:
            stored = replay.changes[0]
            return Versioned(_decoded(DecisionDraft, stored), stored.etag)
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                stored = replay.changes[0]
                return Versioned(_decoded(DecisionDraft, stored), stored.etag)
            view = self._read_view(source, decision_id)
            decision = view.decision.record
            if decision.archived:
                raise _failure("conflict", decision_id, "decision_archived")
            saved = self._versioned_revision(source, decision_id, revision_id).record
            restored = DecisionDraft(
                decision_id=decision_id,
                editor_source=revision_editor_source(saved),
                updated_at=self.clock.utc_now(),
                base_revision_id=revision_id,
            )
            receipt = source.commit(
                operation_id,
                (
                    SourceChange(
                        _key("drafts", decision_id), dump_record(restored), expected_draft_etag
                    ),
                ),
                intent_hash=intent,
            )
        stored = receipt.changes[0]
        return Versioned(_decoded(DecisionDraft, stored), stored.etag)

    def _change_decision(
        self,
        decision_id: str,
        expected_etag: str,
        operation_id: str,
        *,
        name: str | None = None,
        archived: bool | None = None,
    ) -> Versioned[DecisionRecord]:
        decision_id = _valid_id(decision_id)
        _valid_id(operation_id)
        command = (
            "decision.rename"
            if name is not None
            else ("decision.archive" if archived else "decision.restore")
        )
        intent = _intent(command, decision_id, name, str(archived), expected_etag)
        replay = self.source.operation_receipt(operation_id, intent_hash=intent)
        if replay is not None:
            stored = replay.changes[0]
            return Versioned(_decoded(DecisionRecord, stored), stored.etag)
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                stored = replay.changes[0]
                return Versioned(_decoded(DecisionRecord, stored), stored.etag)
            view = self._read_view(source, decision_id)
            decision = view.decision.record
        try:
            changed = DecisionRecord(
                id=decision.id,
                name=decision.name if name is None else name,
                archived=decision.archived if archived is None else archived,
                latest_revision_id=decision.latest_revision_id,
            )
            body = dump_record(changed)
        except (ValidationError, JsonError):
            raise _failure("validation_error", decision_id, "invalid_decision") from None
        receipt = self.source.commit(
            operation_id,
            (SourceChange(_key("decisions", decision_id), body, expected_etag),),
            intent_hash=intent,
        )
        stored = receipt.changes[0]
        return Versioned(_decoded(DecisionRecord, stored), stored.etag)

    @staticmethod
    def _definition(source: str, decision_id: str) -> ChoiceDefinition:
        try:
            value = parse_json(source)
            if isinstance(value, dict):
                schema_source = value.get("input_schema_source")
                if isinstance(schema_source, str):
                    compile_schema(schema_source)
            return load_record(ChoiceDefinition, source)
        except JsonError as error:
            raise _failure("validation_error", decision_id, error.code) from None

    @staticmethod
    def _read_view(source: ProjectSource, decision_id: str) -> DecisionView:
        decision, decision_etag = _required(source, DecisionRecord, _key("decisions", decision_id))
        draft, draft_etag = _required(source, DecisionDraft, _key("drafts", decision_id))
        if draft.decision_id != decision.id:
            raise _failure("validation_error", decision_id, "decision_identity_mismatch")
        return DecisionView(Versioned(decision, decision_etag), Versioned(draft, draft_etag))

    @staticmethod
    def _view_from_receipt(decision_id: str, records: tuple[StoredRecord, ...]) -> DecisionView:
        by_collection = {item.key.collection: item for item in records}
        try:
            decision = by_collection["decisions"]
            draft = by_collection["drafts"]
        except KeyError:
            raise _failure("internal_error", decision_id, "incomplete_commit_receipt") from None
        return DecisionView(
            Versioned(_decoded(DecisionRecord, decision), decision.etag),
            Versioned(_decoded(DecisionDraft, draft), draft.etag),
        )

    @staticmethod
    def _versioned_revision(
        source: ProjectSource, decision_id: str, revision_id: str
    ) -> Versioned[DecisionRevision]:
        record, etag = _required(
            source, DecisionRevision, _key("revisions", revision_id, (decision_id,))
        )
        if (
            record.decision_id != decision_id
            or definition_hash(record.definition) != record.content_hash
        ):
            raise _failure("validation_error", revision_id, "revision_hash_mismatch")
        return Versioned(record, etag)

    def _resolve_definition(self, decision_id: str, selector: str) -> ChoiceDefinition:
        if selector == "draft":
            return self.validate(decision_id)
        saved = self.revision(decision_id, selector).record
        return saved.definition

    def _incompatible_references(
        self, decision_id: str, definition: ChoiceDefinition
    ) -> tuple[IncompatibleReference, ...]:
        with self.source.consistent_read() as source:
            return self._incompatible_references_from(source, decision_id, definition)

    @staticmethod
    def _incompatible_references_from(
        source: ProjectSource, decision_id: str, definition: ChoiceDefinition
    ) -> tuple[IncompatibleReference, ...]:
        found: list[IncompatibleReference] = []
        for dataset_id in source.list_ids("datasets"):
            for label_id in source.list_ids("labels", (decision_id, dataset_id)):
                label, _ = _required(
                    source, LabelRecord, _key("labels", label_id, (decision_id, dataset_id))
                )
                missing = missing_options(
                    definition, label.question_id, label.acceptable_option_ids
                )
                if missing:
                    found.append(
                        IncompatibleReference(
                            kind="label",
                            resource_id=label.id,
                            decision_id=decision_id,
                            dataset_id=label.dataset_id,
                            case_id=label.case_id,
                            question_id=label.question_id,
                            missing_option_ids=missing,
                        )
                    )
        for regression_id in source.list_ids("regressions"):
            regression, _ = _required(source, RegressionRecord, _key("regressions", regression_id))
            revision_key = _key("revisions", regression.decision_revision_id, (decision_id,))
            if source.read(revision_key) is None:
                continue
            _required(source, DecisionRevision, revision_key)
            missing = missing_options(
                definition, regression.question_id, regression.acceptable_option_ids
            )
            if missing:
                found.append(
                    IncompatibleReference(
                        kind="regression",
                        resource_id=regression.id,
                        decision_id=decision_id,
                        dataset_id=regression.dataset_id,
                        case_id=regression.case_id,
                        question_id=regression.question_id,
                        missing_option_ids=missing,
                    )
                )
        return tuple(
            sorted(
                found,
                key=lambda item: (
                    item.kind,
                    item.dataset_id,
                    item.case_id,
                    item.question_id,
                    item.resource_id,
                ),
            )
        )

    def review_references(
        self, decision_id: str, definition: ChoiceDefinition
    ) -> tuple[IncompatibleReference, ...]:
        """Public read-only reference impact seam for one candidate definition."""
        _valid_id(decision_id)
        with self.source.consistent_read() as source:
            return self._incompatible_references_from(source, decision_id, definition)

    def review_draft_transform(
        self,
        decision_id: str,
        editor_source: str,
        edit: EditorEditV1,
        *,
        expected_draft_etag: str,
    ) -> DraftTransformReviewV1:
        """Review a proposed editor change against its current draft and references."""
        decision_id = _valid_id(decision_id)
        with self.source.consistent_read() as source:
            view = self._read_view(source, decision_id)
            if view.draft.etag != expected_draft_etag:
                raise _failure("conflict", decision_id, "draft_changed")
            transformed = transform_editor(editor_source, edit)
            if transformed.projection.form is None or transformed.projection.validation_advice:
                references = None
            else:
                definition = self._definition(transformed.editor_source, decision_id)
                references = self._incompatible_references_from(source, decision_id, definition)
            return DraftTransformReviewV1(transformed, references)
