"""Immutable import previews and all-or-explicit-partial transactional commits."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, cast

from pydantic import ValidationError

from deykit.application.dataset_support import (
    DatasetView,
    cases,
    decoded,
    fail,
    fingerprint,
    identifier,
    intent,
    required,
    safe_hash,
)
from deykit.application.datasets import DatasetService
from deykit.application.errors import ServiceFailure
from deykit.application.import_rows import mapped, rows, source_text
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import (
    JsonDocument,
    JsonError,
    JsonValue,
    bytes_hash,
    parse_json,
)
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
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    LabelChange,
    LabelRecord,
)
from deykit.domain.definitions import definition_hash, select_input
from deykit.domain.import_mapping import ImportMapping
from deykit.domain.label_identity import label_id


@dataclass(frozen=True)
class ImportRow:
    row: int
    source_line: int
    case: CaseRecord | None
    acceptable_option_ids: tuple[str, ...] = ()
    errors: tuple[ServiceError, ...] = ()
    duplicate_input_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportPreview:
    dataset_id: str
    dataset_etag: str
    source_text: str
    source_hash: str
    format: Literal["csv", "jsonl"]
    mapping: ImportMapping
    mapping_hash: str
    decision_id: str | None
    decision_selector: str
    context_hash: str
    question_id: str | None
    rows: tuple[ImportRow, ...]
    preview_hash: str

    @property
    def valid_rows(self) -> tuple[ImportRow, ...]:
        return tuple(row for row in self.rows if not row.errors)

    @property
    def exclusions(self) -> tuple[ImportRow, ...]:
        return tuple(row for row in self.rows if row.errors)


@dataclass(frozen=True)
class ImportCommit:
    dataset: DatasetView
    imported_case_ids: tuple[str, ...]
    exclusions: tuple[ImportRow, ...]
    duplicate_rows: tuple[ImportRow, ...]
    replayed: bool


@dataclass(frozen=True)
class _Context:
    definition: ChoiceDefinition | None
    records: tuple[StoredRecord, ...]


def _preview_hash(preview: ImportPreview) -> str:
    row_hashes = [
        safe_hash(
            {
                "row": item.row,
                "line": item.source_line,
                "case_hash": bytes_hash(dump_record(item.case)) if item.case else None,
                "expected": list(item.acceptable_option_ids),
                "errors": [cast(JsonValue, error.model_dump(mode="json")) for error in item.errors],
                "duplicates": list(item.duplicate_input_ids),
            }
        )
        for item in preview.rows
    ]
    return safe_hash(
        {
            "dataset": preview.dataset_id,
            "etag": preview.dataset_etag,
            "source": preview.source_hash,
            "format": preview.format,
            "mapping": preview.mapping_hash,
            "decision": preview.decision_id,
            "selector": preview.decision_selector,
            "context": preview.context_hash,
            "question": preview.question_id,
            "rows_hash": bytes_hash("\n".join(row_hashes).encode("ascii")),
        }
    )


class ImportService:
    def __init__(
        self, source: ProjectSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory
        self.datasets = DatasetService(source, clock, id_factory)

    @staticmethod
    def parse_mapping(source: str | bytes) -> ImportMapping:
        try:
            return load_record(ImportMapping, source)
        except JsonError as error:
            fail(error.code)

    def preview(
        self,
        dataset_id: str,
        source: str | bytes,
        *,
        format: Literal["csv", "jsonl"],
        mapping: ImportMapping,
        decision_id: str | None = None,
        decision_selector: str = "draft",
    ) -> ImportPreview:
        identifier(dataset_id)
        if decision_id is not None:
            identifier(decision_id)
        try:
            mapping = ImportMapping.model_validate(mapping.model_dump())
        except (ValueError, ValidationError):
            fail("invalid_import_mapping")
        if mapping.expected_column is not None and decision_id is None:
            fail("expectations_require_decision")
        text = source_text(source)
        with self.source.consistent_read():
            return self._preview(dataset_id, text, format, mapping, decision_id, decision_selector)

    def _context_records(self, decision_id: str | None, selector: str) -> tuple[StoredRecord, ...]:
        if decision_id is None:
            if selector != "draft":
                fail("revision_requires_decision")
            return ()
        pointer = required(self.source, ResourceKey("decisions", decision_id))
        key = (
            ResourceKey("drafts", decision_id)
            if selector == "draft"
            else ResourceKey("revisions", identifier(selector), (decision_id,))
        )
        return pointer, required(self.source, key)

    def _context(self, decision_id: str | None, selector: str) -> _Context:
        if decision_id is None:
            if selector != "draft":
                fail("revision_requires_decision")
            return _Context(None, ())
        pointer = required(self.source, ResourceKey("decisions", decision_id))
        decision = decoded(DecisionRecord, pointer)
        if decision.archived:
            fail("decision_archived", "conflict")
        try:
            if selector == "draft":
                stored = required(self.source, ResourceKey("drafts", decision_id))
                draft = decoded(DecisionDraft, stored)
                definition = load_record(ChoiceDefinition, draft.editor_source)
            else:
                stored = required(
                    self.source, ResourceKey("revisions", identifier(selector), (decision_id,))
                )
                revision = decoded(DecisionRevision, stored)
                definition = revision.definition
                if definition_hash(definition) != revision.content_hash:
                    fail("revision_hash_mismatch")
        except JsonError as error:
            fail(error.code)
        return _Context(definition, (pointer, stored))

    def _fingerprinted_records(
        self, dataset_id: str, decision_id: str | None, selector: str
    ) -> tuple[StoredRecord, ...]:
        context_records = self._context_records(decision_id, selector)
        labels: tuple[StoredRecord, ...] = ()
        if decision_id is not None:
            scope = (decision_id, dataset_id)
            labels = tuple(
                required(self.source, ResourceKey("labels", key, scope))
                for key in self.source.list_ids("labels", scope)
            )
        return (
            required(self.source, ResourceKey("datasets", dataset_id)),
            *cases(self.source, dataset_id),
            *context_records,
            *labels,
        )

    def _preview(
        self,
        dataset_id: str,
        text: str,
        format: Literal["csv", "jsonl"],
        mapping: ImportMapping,
        decision_id: str | None,
        selector: str,
    ) -> ImportPreview:
        dataset = self.datasets.read(dataset_id)
        DatasetService.check_etag(dataset, dataset.etag)
        context = self._context(decision_id, selector)
        before = self._fingerprinted_records(dataset_id, decision_id, selector)
        source_hash = bytes_hash(text.encode("utf-8"))
        mapping_hash = safe_hash(cast(JsonValue, mapping.model_dump(mode="json")))
        current = cases(self.source, dataset_id)
        existing_ids = {stored.key.resource_id.casefold() for stored in current}
        seen_inputs: dict[str, list[str]] = {}
        for stored in current:
            case = decoded(CaseRecord, stored)
            seen_inputs.setdefault(safe_hash(parse_json(case.input_source)), []).append(case.id)
        question = context.definition.questions[0] if context.definition else None
        valid_options = {option.id for option in question.options} if question else set()
        results: list[ImportRow] = []
        for source_row in rows(text, format):
            if source_row.error is not None:
                results.append(
                    ImportRow(source_row.row, source_row.line, None, errors=(source_row.error,))
                )
                continue
            try:
                if source_row.value is None:
                    fail("invalid_import_row")
                supplied_id, value, expected = mapped(source_row.value, mapping)
                generated_id = "case-" + safe_hash(
                    [dataset_id, source_hash, mapping_hash, source_row.row]
                )
                case = DatasetService.case_record(
                    dataset_id, identifier(supplied_id or generated_id), value
                )
                if context.definition is not None:
                    select_input(context.definition, JsonDocument(case.input_source))
                if any(option not in valid_options for option in expected):
                    fail("unknown_expected_option")
                results.append(ImportRow(source_row.row, source_row.line, case, expected))
            except (ServiceFailure, JsonError, ValidationError) as error:
                reason = (
                    error.error.reason
                    if isinstance(error, ServiceFailure)
                    else error.code
                    if isinstance(error, JsonError)
                    else "invalid_import_row"
                )
                results.append(
                    ImportRow(
                        source_row.row,
                        source_row.line,
                        None,
                        errors=(
                            ServiceError(
                                code="validation_error", row=source_row.row, reason=reason
                            ),
                        ),
                    )
                )
        counts = Counter(row.case.id.casefold() for row in results if row.case is not None)
        identified: list[ImportRow] = []
        for row in results:
            if row.case is None:
                identified.append(row)
                continue
            if row.case.id.casefold() in existing_ids or counts[row.case.id.casefold()] > 1:
                identified.append(
                    replace(
                        row,
                        errors=(
                            ServiceError(code="conflict", row=row.row, reason="case_id_conflict"),
                        ),
                    )
                )
                continue
            input_hash = safe_hash(parse_json(row.case.input_source))
            seen_inputs.setdefault(input_hash, []).append(row.case.id)
            identified.append(row)
        results = [
            replace(
                row,
                duplicate_input_ids=tuple(
                    sorted(
                        other
                        for other in seen_inputs.get(
                            safe_hash(parse_json(row.case.input_source)), []
                        )
                        if other != row.case.id
                    )
                ),
            )
            if row.case is not None and not row.errors
            else row
            for row in identified
        ]
        after = self._fingerprinted_records(dataset_id, decision_id, selector)
        if fingerprint(before) != fingerprint(after):
            fail("unstable_import_context", "conflict")
        preview = ImportPreview(
            dataset_id,
            dataset.etag,
            text,
            source_hash,
            format,
            mapping,
            mapping_hash,
            decision_id,
            selector,
            fingerprint(before),
            question.id if question else None,
            tuple(results),
            "",
        )
        return replace(preview, preview_hash=_preview_hash(preview))

    def commit(
        self, preview: ImportPreview, *, operation_id: str, skip_invalid: bool = False
    ) -> ImportCommit:
        identifier(operation_id)
        if type(skip_invalid) is not bool:
            fail("invalid_partial_import_choice")
        if (
            preview.source_hash != bytes_hash(source_text(preview.source_text).encode("utf-8"))
            or preview.mapping_hash
            != safe_hash(cast(JsonValue, preview.mapping.model_dump(mode="json")))
            or preview.preview_hash != _preview_hash(preview)
        ):
            fail("invalid_import_preview")
        digest = intent("import.commit", [preview.preview_hash, skip_invalid])
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self._result(preview, replay)
            if preview.exclusions and not skip_invalid:
                fail("import_rows_invalid")
            if not preview.valid_rows:
                fail("import_has_no_valid_rows")
            current_hash = fingerprint(
                self._fingerprinted_records(
                    preview.dataset_id, preview.decision_id, preview.decision_selector
                )
            )
            if current_hash != preview.context_hash:
                fail("import_context_changed", "conflict")
            fresh = self._preview(
                preview.dataset_id,
                preview.source_text,
                preview.format,
                preview.mapping,
                preview.decision_id,
                preview.decision_selector,
            )
            if fresh.preview_hash != preview.preview_hash:
                fail("import_context_changed", "conflict")
            changes: list[SourceChange] = []
            for row in preview.valid_rows:
                if row.case is None:
                    fail("invalid_import_preview")
                case = row.case
                changes.append(
                    SourceChange(
                        ResourceKey("cases", case.id, (preview.dataset_id,)),
                        dump_record(case),
                        None,
                    )
                )
                if row.acceptable_option_ids:
                    if preview.decision_id is None or preview.question_id is None:
                        fail("invalid_import_preview")
                    label = LabelRecord(
                        id=label_id(case.id, preview.question_id),
                        decision_id=preview.decision_id,
                        dataset_id=preview.dataset_id,
                        case_id=case.id,
                        question_id=preview.question_id,
                        input_hash=safe_hash(parse_json(case.input_source)),
                        acceptable_option_ids=row.acceptable_option_ids,
                        provenance="imported_unknown",
                        updated_at=self.clock.utc_now(),
                    )
                    change = LabelChange(
                        id=identifier(self.id_factory()),
                        operation_id=operation_id,
                        decision_id=label.decision_id,
                        dataset_id=label.dataset_id,
                        case_id=label.case_id,
                        question_id=label.question_id,
                        action="set",
                        label=label,
                        created_at=self.clock.utc_now(),
                    )
                    scope = (preview.decision_id, preview.dataset_id)
                    changes += [
                        SourceChange(
                            ResourceKey("labels", label.id, scope), dump_record(label), None
                        ),
                        SourceChange(
                            ResourceKey("label_history", change.id, scope),
                            dump_record(change),
                            None,
                        ),
                    ]
            dataset = self.datasets.read(preview.dataset_id)
            changes.append(
                SourceChange(
                    ResourceKey("datasets", preview.dataset_id),
                    dump_record(self.datasets.bump(dataset.record)),
                    preview.dataset_etag,
                )
            )
            if (
                fingerprint(
                    self._fingerprinted_records(
                        preview.dataset_id, preview.decision_id, preview.decision_selector
                    )
                )
                != preview.context_hash
            ):
                fail("import_context_changed", "conflict")
            receipt = self.source.commit(operation_id, tuple(changes), intent_hash=digest)
        return self._result(preview, receipt)

    @staticmethod
    def _result(preview: ImportPreview, receipt: CommitReceipt) -> ImportCommit:
        return ImportCommit(
            DatasetService.from_receipt(receipt),
            tuple(row.case.id for row in preview.valid_rows if row.case is not None),
            preview.exclusions,
            tuple(row for row in preview.valid_rows if row.duplicate_input_ids),
            receipt.replayed,
        )
