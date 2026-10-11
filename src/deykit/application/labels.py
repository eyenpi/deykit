"""Decision-scoped label review and atomic explicit saves, without predictions."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from deykit.application import label_validation as admission
from deykit.application.dataset_support import decoded, fail, identifier, intent, page, required
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue
from deykit.contracts.ports import (
    Clock,
    CommitReceipt,
    ProjectSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    DatasetRecord,
    DecisionDraft,
    DecisionRecord,
    LabelChange,
    LabelRecord,
)
from deykit.domain.definitions import ApplicabilityReason, label_applicability, missing_options
from deykit.domain.label_identity import label_id

Provenance = Literal["human", "authored_fixture", "imported_unknown", "model_generated"]
Action = Literal["set", "clear", "dispute", "resolve"]


def admit_label_record(stored: StoredRecord) -> LabelRecord:
    """Decode a current label and enforce its canonical key and scope."""
    label = decoded(LabelRecord, stored)
    expected = ResourceKey(
        "labels",
        label_id(label.case_id, label.question_id),
        (label.decision_id, label.dataset_id),
    )
    if stored.key != expected or label.id != expected.resource_id:
        fail("label_identity_mismatch")
    return label


@dataclass(frozen=True)
class LabelReview:
    """Optimistic tokens captured alongside the full input and choice shown to the reviewer."""

    decision_id: str
    dataset_id: str
    case_id: str
    question_id: str
    input_hash: str
    decision_etag: str
    draft_etag: str
    label_etag: str | None


@dataclass(frozen=True)
class LabelView:
    review: LabelReview
    case: CaseRecord
    definition: ChoiceDefinition
    label: LabelRecord | None
    reasons: tuple[ApplicabilityReason, ...]
    missing_option_ids: tuple[str, ...]

    @property
    def status(self) -> str:
        return "unlabelled" if self.label is None else "excluded" if self.reasons else "applicable"


@dataclass(frozen=True)
class LabelPage:
    items: tuple[LabelView, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class LabelEdit:
    review: LabelReview
    action: Action
    acceptable_option_ids: tuple[str, ...] = ()
    provenance: Provenance | None = None
    note: str | None = None


@dataclass(frozen=True)
class LabelMutation:
    changes: tuple[LabelChange, ...]
    replayed: bool


class LabelService:
    def __init__(
        self,
        source: ProjectSource,
        clock: Clock,
        id_factory: Callable[[], str] = new_id,
        *,
        capture_snapshot: Callable[[], tuple[StoredRecord, ...]] | None = None,
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory
        self.capture_snapshot = capture_snapshot

    def _context(self, decision_id: str) -> tuple[ChoiceDefinition, str, str]:
        decision = required(self.source, ResourceKey("decisions", identifier(decision_id)))
        decoded(DecisionRecord, decision)
        draft = required(self.source, ResourceKey("drafts", decision_id))
        return self._context_from_records(decision, draft)

    @staticmethod
    def _context_from_records(
        decision: StoredRecord, draft: StoredRecord
    ) -> tuple[ChoiceDefinition, str, str]:
        decoded(DecisionRecord, decision)
        try:
            definition = load_record(ChoiceDefinition, decoded(DecisionDraft, draft).editor_source)
        except (JsonError, ValidationError):
            fail("invalid_decision_draft")
        return definition, decision.etag, draft.etag

    @staticmethod
    def _view_from_records(
        decision_id: str,
        dataset_id: str,
        case_id: str,
        question_id: str,
        definition: ChoiceDefinition,
        decision_etag: str,
        draft_etag: str,
        case: CaseRecord,
        stored_label: StoredRecord | None,
    ) -> LabelView:
        label = admit_label_record(stored_label) if stored_label else None
        if label is not None and (
            label.decision_id,
            label.dataset_id,
            label.case_id,
            label.question_id,
        ) != (decision_id, dataset_id, case_id, question_id):
            fail("label_identity_mismatch")
        input_hash = JsonDocument(case.input_source).content_hash
        review = LabelReview(
            decision_id,
            dataset_id,
            case_id,
            question_id,
            input_hash,
            decision_etag,
            draft_etag,
            stored_label.etag if stored_label else None,
        )
        return LabelView(
            review,
            case,
            definition,
            label,
            label_applicability(label, definition, input_hash) if label else (),
            missing_options(definition, question_id, label.acceptable_option_ids) if label else (),
        )

    def read(
        self, decision_id: str, dataset_id: str, case_id: str, *, question_id: str | None = None
    ) -> LabelView:
        self._read_controls(decision_id, dataset_id, case_id, question_id)
        with self.source.consistent_read():
            definition, decision_etag, draft_etag = self._context(decision_id)
            required(self.source, ResourceKey("datasets", identifier(dataset_id)))
            case = decoded(
                CaseRecord,
                required(self.source, ResourceKey("cases", identifier(case_id), (dataset_id,))),
            )
            question = question_id if question_id is not None else definition.questions[0].id
            stored = self.source.read(
                ResourceKey("labels", label_id(case_id, question), (decision_id, dataset_id))
            )
            return self._view_from_records(
                decision_id,
                dataset_id,
                case_id,
                question,
                definition,
                decision_etag,
                draft_etag,
                case,
                stored,
            )

    def list(
        self,
        decision_id: str,
        dataset_id: str,
        *,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> LabelPage:
        admission.resource(decision_id)
        admission.resource(dataset_id)
        if status is not None:
            admission.choice(
                status,
                ("applicable", "unlabelled", "disputed", "stale", "incompatible"),
                "invalid_label_status",
            )
        if cursor is not None:
            admission.resource(cursor)
        if not 1 <= admission.integer(limit, "invalid_page_limit") <= 500:
            fail("invalid_page_limit")
        capture_snapshot = self.capture_snapshot
        if capture_snapshot is not None:
            return self._list_from_snapshot(
                capture_snapshot,
                decision_id,
                dataset_id,
                status=status,
                cursor=cursor,
                limit=limit,
            )
        with self.source.consistent_read():
            definition, _, _ = self._context(decision_id)
            required(self.source, ResourceKey("datasets", identifier(dataset_id)))
            pairs = {
                (case_id, definition.questions[0].id)
                for case_id in self.source.list_ids("cases", (dataset_id,))
            }
            for key in self.source.list_ids("labels", (decision_id, dataset_id)):
                label = self._label(
                    required(self.source, ResourceKey("labels", key, (decision_id, dataset_id)))
                )
                pairs.add((label.case_id, label.question_id))
            views = {
                label_id(case, question): self.read(
                    decision_id, dataset_id, case, question_id=question
                )
                for case, question in sorted(pairs)
            }
            visible = tuple(
                key
                for key, view in views.items()
                if status is None or status == view.status or status in view.reasons
            )
            chosen, next_cursor = page(visible, cursor, limit)
            return LabelPage(tuple(views[key] for key in chosen), len(visible), next_cursor)

    def _list_from_snapshot(
        self,
        capture_snapshot: Callable[[], tuple[StoredRecord, ...]],
        decision_id: str,
        dataset_id: str,
        *,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> LabelPage:
        with self.source.consistent_read():
            records = capture_snapshot()
            index: dict[ResourceKey, StoredRecord] = {}
            scoped_ids: dict[tuple[str, tuple[str, ...]], list[str]] = {}
            for record in records:
                if record.key in index:
                    fail("duplicate_captured_key", "incompatible_data")
                index[record.key] = record
                scoped_ids.setdefault((record.key.collection, record.key.scope), []).append(
                    record.key.resource_id
                )

            def snapshot_required(key: ResourceKey) -> StoredRecord:
                record = index.get(key)
                if record is None:
                    raise ServiceFailure(
                        ServiceError(code="not_found", resource_id=key.resource_id)
                    )
                return record

            definition, decision_etag, draft_etag = self._context_from_records(
                snapshot_required(ResourceKey("decisions", identifier(decision_id))),
                snapshot_required(ResourceKey("drafts", decision_id)),
            )
            dataset_stored = snapshot_required(ResourceKey("datasets", identifier(dataset_id)))
            decoded(DatasetRecord, dataset_stored)

            case_ids = scoped_ids.get(("cases", (dataset_id,)), [])
            cases: dict[str, CaseRecord] = {}
            for case_key in case_ids:
                stored_case = snapshot_required(ResourceKey("cases", case_key, (dataset_id,)))
                decoded_case = decoded(CaseRecord, stored_case)
                if decoded_case.id != case_key or decoded_case.dataset_id != dataset_id:
                    fail("invalid_record")
                cases[case_key] = decoded_case

            pairs = {(case_key, definition.questions[0].id) for case_key in case_ids}
            labels: dict[tuple[str, str], StoredRecord] = {}
            for label_key in scoped_ids.get(("labels", (decision_id, dataset_id)), []):
                stored_label = snapshot_required(
                    ResourceKey("labels", label_key, (decision_id, dataset_id))
                )
                label = self._label(stored_label)
                pair = (label.case_id, label.question_id)
                labels[pair] = stored_label
                pairs.add(pair)

            views: dict[str, LabelView] = {}
            for case_key, question_key in sorted(pairs):
                case = cases.get(case_key)
                if case is None:
                    case = decoded(
                        CaseRecord,
                        snapshot_required(ResourceKey("cases", case_key, (dataset_id,))),
                    )
                    if case.id != case_key or case.dataset_id != dataset_id:
                        fail("invalid_record")
                view = self._view_from_records(
                    decision_id,
                    dataset_id,
                    case_key,
                    question_key,
                    definition,
                    decision_etag,
                    draft_etag,
                    case,
                    labels.get((case_key, question_key)),
                )
                views[label_id(case_key, question_key)] = view

            visible = tuple(
                key
                for key, view in sorted(views.items())
                if status is None or status == view.status or status in view.reasons
            )
            chosen, next_cursor = page(visible, cursor, limit)
            return LabelPage(tuple(views[key] for key in chosen), len(visible), next_cursor)

    def history(
        self, decision_id: str, dataset_id: str, case_id: str, *, question_id: str | None = None
    ) -> tuple[LabelChange, ...]:
        self._read_controls(decision_id, dataset_id, case_id, question_id)
        scope = (decision_id, dataset_id)
        with self.source.consistent_read():
            records = (
                decoded(
                    LabelChange, required(self.source, ResourceKey("label_history", key, scope))
                )
                for key in self.source.list_ids("label_history", scope)
            )
            return tuple(
                sorted(
                    (
                        r
                        for r in records
                        if r.case_id == case_id
                        and (question_id is None or r.question_id == question_id)
                    ),
                    key=lambda r: (r.created_at, r.id),
                )
            )

    def set(
        self,
        review: LabelReview,
        acceptable_option_ids: tuple[str, ...],
        *,
        provenance: Provenance | None = None,
        note: str | None = None,
        operation_id: str,
    ) -> LabelMutation:
        return self.batch(
            (LabelEdit(review, "set", acceptable_option_ids, provenance, note),),
            operation_id=operation_id,
        )

    def clear(self, review: LabelReview, *, operation_id: str) -> LabelMutation:
        return self.batch((LabelEdit(review, "clear"),), operation_id=operation_id)

    def dispute(self, review: LabelReview, *, reason: str, operation_id: str) -> LabelMutation:
        return self.batch((LabelEdit(review, "dispute", note=reason),), operation_id=operation_id)

    def resolve(
        self,
        review: LabelReview,
        acceptable_option_ids: tuple[str, ...],
        *,
        provenance: Provenance | None = None,
        note: str | None = None,
        operation_id: str,
    ) -> LabelMutation:
        return self.batch(
            (LabelEdit(review, "resolve", acceptable_option_ids, provenance, note),),
            operation_id=operation_id,
        )

    def batch(self, edits: tuple[LabelEdit, ...], *, operation_id: str) -> LabelMutation:
        admission.resource(operation_id)
        self._admit_edits(edits)
        try:
            values: list[JsonValue] = []
            for edit in edits:
                r = edit.review
                values.append(
                    [
                        r.decision_id,
                        r.dataset_id,
                        r.case_id,
                        r.question_id,
                        r.input_hash,
                        r.decision_etag,
                        r.draft_etag,
                        r.label_etag,
                        edit.action,
                        list(edit.acceptable_option_ids),
                        edit.provenance,
                        edit.note,
                    ]
                )
            digest = intent("label.batch", values)
        except (AttributeError, TypeError, ValueError):
            fail("invalid_label_batch")
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self._result(replay)
            if not isinstance(edits, tuple) or not edits:
                fail("empty_label_batch")
            targets = [
                (r.review.decision_id, r.review.dataset_id, r.review.case_id, r.review.question_id)
                for r in edits
            ]
            if len(set(targets)) != len(targets):
                fail("duplicate_label_target")
            prepared: list[tuple[LabelEdit, LabelView]] = []
            for edit in edits:
                r = edit.review
                view = self.read(r.decision_id, r.dataset_id, r.case_id, question_id=r.question_id)
                if view.review != r:
                    fail("label_review_changed", "conflict")
                dataset = decoded(
                    DatasetRecord, required(self.source, ResourceKey("datasets", r.dataset_id))
                )
                decision = decoded(
                    DecisionRecord, required(self.source, ResourceKey("decisions", r.decision_id))
                )
                if decision.archived:
                    fail("decision_archived", "conflict")
                if dataset.archived:
                    fail("dataset_archived", "conflict")
                self._validate(edit, view)
                prepared.append((edit, view))
            changes: list[SourceChange] = []
            for edit, view in prepared:
                r, previous = edit.review, view.label
                label: LabelRecord | None = None
                if edit.action != "clear":
                    try:
                        label = LabelRecord(
                            id=label_id(r.case_id, r.question_id),
                            decision_id=r.decision_id,
                            dataset_id=r.dataset_id,
                            case_id=r.case_id,
                            question_id=r.question_id,
                            input_hash=(
                                previous.input_hash
                                if edit.action == "dispute" and previous
                                else r.input_hash
                            ),
                            acceptable_option_ids=(
                                previous.acceptable_option_ids
                                if edit.action == "dispute" and previous
                                else tuple(sorted(edit.acceptable_option_ids))
                            ),
                            status=(
                                "disputed"
                                if edit.action == "dispute"
                                else previous.status
                                if previous and edit.action == "set"
                                else "active"
                            ),
                            provenance=edit.provenance
                            or (previous.provenance if previous else "human"),
                            updated_at=self.clock.utc_now(),
                            note=edit.note
                            if edit.note is not None
                            else previous.note
                            if previous
                            else "",
                        )
                    except (ValueError, ValidationError):
                        fail("invalid_label")
                scope = (r.decision_id, r.dataset_id)
                if label is not None or previous is not None:
                    changes.append(
                        SourceChange(
                            ResourceKey("labels", label_id(r.case_id, r.question_id), scope),
                            dump_record(label) if label else None,
                            r.label_etag,
                        )
                    )
                change = LabelChange(
                    id=identifier(self.id_factory()),
                    operation_id=operation_id,
                    decision_id=r.decision_id,
                    dataset_id=r.dataset_id,
                    case_id=r.case_id,
                    question_id=r.question_id,
                    action=edit.action,
                    label=label,
                    created_at=self.clock.utc_now(),
                )
                changes.append(
                    SourceChange(
                        ResourceKey("label_history", change.id, scope), dump_record(change), None
                    )
                )
            # Detect external source edits during preparation, too. Cooperating writers are locked.
            for edit, _ in prepared:
                r = edit.review
                if (
                    self.read(
                        r.decision_id, r.dataset_id, r.case_id, question_id=r.question_id
                    ).review
                    != r
                ):
                    fail("label_review_changed", "conflict")
            return self._result(
                self.source.commit(operation_id, tuple(changes), intent_hash=digest)
            )

    @staticmethod
    def _read_controls(
        decision_id: str, dataset_id: str, case_id: str, question_id: str | None
    ) -> None:
        for value in (decision_id, dataset_id, case_id):
            admission.resource(value)
        if question_id is not None:
            admission.resource(question_id)

    @staticmethod
    def _label(stored: StoredRecord) -> LabelRecord:
        return admit_label_record(stored)

    @staticmethod
    def _admit_edits(edits: tuple[LabelEdit, ...]) -> None:
        for edit in admission.sequence(edits, "invalid_label_batch"):
            raw = admission.dto(edit, LabelEdit, "invalid_label_edit")
            review = admission.dto(raw["review"], LabelReview, "invalid_label_review")
            for name in ("decision_id", "dataset_id", "case_id", "question_id"):
                admission.resource(review[name])
            for name in ("input_hash", "decision_etag", "draft_etag"):
                admission.content_hash(review[name])
            if review["label_etag"] is not None:
                admission.content_hash(review["label_etag"])
            admission.choice(
                raw["action"], ("set", "clear", "dispute", "resolve"), "invalid_label_action"
            )
            for option in admission.sequence(
                raw["acceptable_option_ids"], "invalid_acceptable_set"
            ):
                admission.resource(option)
            if raw["provenance"] is not None:
                admission.choice(
                    raw["provenance"],
                    ("human", "authored_fixture", "imported_unknown", "model_generated"),
                    "invalid_provenance",
                )
            if raw["note"] is not None:
                admission.text(raw["note"], "invalid_label_note")

    @staticmethod
    def _validate(edit: LabelEdit, view: LabelView) -> None:
        if edit.action in {"set", "resolve"}:
            if view.label is None and edit.provenance is None:
                fail("new_label_requires_provenance")
            if not edit.acceptable_option_ids:
                fail("empty_acceptable_set")
            if len(set(edit.acceptable_option_ids)) != len(edit.acceptable_option_ids):
                fail("duplicate_acceptable_option")
            if missing_options(
                view.definition, edit.review.question_id, edit.acceptable_option_ids
            ):
                fail("unknown_expected_option")
        elif edit.acceptable_option_ids or edit.provenance is not None:
            fail("unexpected_label_fields")
        if edit.action == "dispute" and (
            view.label is None or not edit.note or not edit.note.strip()
        ):
            fail("dispute_requires_label_and_reason")
        if edit.action == "clear" and edit.note is not None:
            fail("unexpected_label_fields")

    @staticmethod
    def _result(receipt: CommitReceipt) -> LabelMutation:
        return LabelMutation(
            tuple(
                decoded(LabelChange, r)
                for r in receipt.changes
                if r.key.collection == "label_history"
            ),
            receipt.replayed,
        )
