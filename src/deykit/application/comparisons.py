"""Persist comparisons of immutable evaluations over the source and clock ports."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from deykit.application.dataset_support import fail, identifier, page
from deykit.application.evaluations import (
    EvaluationView,
    FrozenEvaluation,
    admit_evaluation_record,
    frozen_evaluation_from_records,
)
from deykit.comparisons.models import (
    ComparisonCaseSide,
    ComparisonContext,
    ComparisonOutcomes,
    Status,
)
from deykit.comparisons.pairing import pair_cases
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import JsonError, parse_json, semantic_hash
from deykit.contracts.model_admission import ModelInvalid
from deykit.contracts.ports import Clock, ResourceKey, SnapshotSource, SourceChange, StoredRecord
from deykit.contracts.records import ComparisonRecord, PreparedCase
from deykit.domain.case_identity import image_treatment_hash
from deykit.metrics import assess_results
from deykit.metrics.summary import MetricsInvalid


@dataclass(frozen=True)
class ComparisonView:
    record: ComparisonRecord
    etag: str
    outcomes: ComparisonOutcomes
    replayed: bool = False


@dataclass(frozen=True)
class ComparisonPage:
    items: tuple[ComparisonView, ...]
    total: int
    next_cursor: str | None


def comparison_hash(record: ComparisonRecord) -> str:
    return semantic_hash(
        {
            "profile": "deykit-comparison-v1",
            "left_evaluation_id": record.left_evaluation_id,
            "right_evaluation_id": record.right_evaluation_id,
            "left_result_snapshot_id": record.left_result_snapshot_id,
            "right_result_snapshot_id": record.right_result_snapshot_id,
            "outcomes": parse_json(record.outcomes_source),
        }
    )


def _view(stored: StoredRecord, *, replayed: bool = False) -> ComparisonView:
    try:
        record = load_record(ComparisonRecord, stored.body)
        outcomes = load_record(ComparisonOutcomes, record.outcomes_source)
        if (
            record.id != stored.key.resource_id
            or stored.key.collection != "comparisons"
            or stored.key.scope
            or record.content_hash != comparison_hash(record)
            or record.left_evaluation_id != outcomes.left.evaluation_id
            or record.right_evaluation_id != outcomes.right.evaluation_id
            or record.left_result_snapshot_id != outcomes.left.result_snapshot_id
            or record.right_result_snapshot_id != outcomes.right.result_snapshot_id
        ):
            fail("comparison_evidence_mismatch", "incompatible_data")
    except JsonError:
        fail("invalid_comparison_record", "incompatible_data")
    return ComparisonView(record, stored.etag, outcomes, replayed)


def _prepared(
    records: tuple[StoredRecord, ...], frozen: FrozenEvaluation
) -> tuple[PreparedCase, ...]:
    indexed: dict[str, PreparedCase] = {}
    input_hashes = {result.case_id: result.input_hash for result in frozen.results.results}
    for stored in records:
        if stored.key.collection != "prepared_cases" or stored.key.scope != (frozen.manifest.id,):
            continue
        record = load_record(PreparedCase, stored.body)
        if (
            record.run_id != frozen.manifest.id
            or record.case_id != stored.key.resource_id
            or record.case_id not in frozen.manifest.case_ids
            or record.case_id in indexed
            or record.input_hash != input_hashes.get(record.case_id)
            or (
                record.request is not None
                and (
                    record.request.compiler_version != frozen.manifest.compiler_version
                    or record.request.adapter != frozen.manifest.adapter
                    or record.request.requested_model != frozen.manifest.requested_model
                )
            )
        ):
            fail("comparison_prepared_context_mismatch", "incompatible_data")
        indexed[record.case_id] = record
    if set(indexed) != set(frozen.manifest.case_ids):
        fail("comparison_prepared_plan_missing", "incompatible_data")
    return tuple(indexed[case_id] for case_id in frozen.manifest.case_ids)


def _side(
    evaluation: EvaluationView, frozen: FrozenEvaluation, prepared: tuple[PreparedCase, ...]
) -> tuple[ComparisonContext, dict[str, ComparisonCaseSide]]:
    summary = assess_results(
        frozen.revision.definition,
        frozen.dataset,
        frozen.labels,
        frozen.results,
        frozen.manifest.case_ids,
    )
    result_index = {result.case_id: result for result in frozen.results.results}
    case_index = {case.id: case for case in frozen.dataset.cases}
    request_hashes = {
        item.case_id: item.request.body_hash if item.request is not None else None
        for item in prepared
    }
    cases = {
        assessment.case_id: ComparisonCaseSide(
            input_hash=result_index[assessment.case_id].input_hash,
            image_treatment_hash=image_treatment_hash(
                case_index[assessment.case_id], frozen.revision.definition
            ),
            request_hash=request_hashes[assessment.case_id],
            status=cast(Status, assessment.status),
            answer_option_id=assessment.answer_option_id,
            expected_option_ids=assessment.expected_option_ids,
            label_provenance=assessment.label_provenance,
            exclusion_reasons=assessment.exclusion_reasons,
            correct=assessment.set_correct,
        )
        for assessment in summary.cases
    }
    return _context(evaluation, frozen, prepared), cases


def _context(
    evaluation: EvaluationView, frozen: FrozenEvaluation, prepared: tuple[PreparedCase, ...]
) -> ComparisonContext:
    if frozen.manifest.decision_id is None or frozen.manifest.dataset_id is None:
        fail("incomplete_run_manifest", "incompatible_data")
    question = frozen.revision.definition.questions[0]
    return ComparisonContext(
        evaluation_id=evaluation.record.id,
        evaluation_hash=evaluation.record.content_hash,
        evaluation_mode=evaluation.record.mode,
        run_id=frozen.manifest.id,
        decision_id=identifier(frozen.manifest.decision_id),
        dataset_id=identifier(frozen.manifest.dataset_id),
        decision_revision_id=frozen.revision.id,
        definition_hash=frozen.revision.content_hash,
        dataset_snapshot_id=frozen.dataset.id,
        dataset_hash=frozen.dataset.content_hash,
        label_snapshot_id=frozen.labels.id,
        label_hash=frozen.labels.content_hash,
        result_snapshot_id=frozen.results.id,
        result_hash=frozen.results.content_hash,
        evidence_mode=frozen.manifest.mode,
        adapter=frozen.manifest.adapter,
        compiler_ids=tuple(
            sorted({item.request.compiler for item in prepared if item.request is not None})
        ),
        compiler_version=frozen.manifest.compiler_version,
        requested_model=frozen.manifest.requested_model,
        answering_models=tuple(
            sorted(
                {
                    result.answer.reported_model
                    for result in frozen.results.results
                    if result.answer is not None and result.answer.reported_model is not None
                }
            )
        ),
        provider_profile_id=frozen.manifest.provider_profile_id,
        provider_config_hash=frozen.manifest.provider_config_hash,
        question_id=question.id,
        option_ids=tuple(option.id for option in question.options),
        option_order=frozen.manifest.option_order
        or tuple(option.id for option in question.options),
        selected_case_ids=frozen.manifest.case_ids,
    )


def _evaluation(
    records: tuple[StoredRecord, ...], index: dict[ResourceKey, StoredRecord], evaluation_id: str
) -> tuple[EvaluationView, FrozenEvaluation]:
    stored = index.get(ResourceKey("evaluations", evaluation_id))
    if stored is None:
        fail("evaluation_missing", "not_found")
    evaluation = admit_evaluation_record(stored)
    if evaluation.record.id != evaluation_id:
        fail("comparison_evaluation_link_mismatch", "incompatible_data")
    frozen = frozen_evaluation_from_records(
        records,
        evaluation.record.run_id,
        evaluation.record.result_snapshot_id,
        evaluation.record.label_snapshot_id,
        evaluation.record.mode,
    )
    return evaluation, frozen


class ComparisonService:
    def __init__(
        self, source: SnapshotSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory

    def _bound_view(
        self, stored: StoredRecord, records: tuple[StoredRecord, ...], *, replayed: bool = False
    ) -> ComparisonView:
        return admit_comparison_from_records(stored, records, replayed=replayed)

    def create(
        self, left_evaluation_id: str, right_evaluation_id: str, *, operation_id: str
    ) -> ComparisonView:
        identifier(left_evaluation_id), identifier(right_evaluation_id), identifier(operation_id)
        digest = semantic_hash(
            {
                "command": "comparison.create",
                "left_evaluation_id": left_evaluation_id,
                "right_evaluation_id": right_evaluation_id,
            }
        )
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                if len(replay.changes) != 1:
                    fail("invalid_comparison_receipt", "incompatible_data")
                return self._bound_view(
                    replay.changes[0],
                    cast(SnapshotSource, source).capture_snapshot(),
                    replayed=True,
                )
            before = cast(SnapshotSource, source).capture_snapshot()
            index = {item.key: item for item in before}
            try:
                left, left_frozen = _evaluation(before, index, left_evaluation_id)
                right, right_frozen = _evaluation(before, index, right_evaluation_id)
                sides = (
                    _side(left, left_frozen, _prepared(before, left_frozen)),
                    _side(right, right_frozen, _prepared(before, right_frozen)),
                )
                outcomes = pair_cases(sides[0][0], sides[1][0], sides[0][1], sides[1][1])
                provisional = ComparisonRecord(
                    id=identifier(self.id_factory()),
                    left_evaluation_id=left.record.id,
                    right_evaluation_id=right.record.id,
                    left_result_snapshot_id=left.record.result_snapshot_id,
                    right_result_snapshot_id=right.record.result_snapshot_id,
                    outcomes_source=dump_record(outcomes).decode("utf-8"),
                    content_hash="0" * 64,
                    created_at=self.clock.utc_now(),
                )
                record = provisional.model_copy(
                    update={"content_hash": comparison_hash(provisional)}
                )
                body = dump_record(record)
            except (MetricsInvalid, ModelInvalid, JsonError, ValueError):
                fail("incompatible_comparison", "incompatible_data")
            if cast(SnapshotSource, source).capture_snapshot() != before:
                fail("comparison_source_changed", "conflict")
            receipt = source.commit(
                operation_id,
                (SourceChange(ResourceKey("comparisons", record.id), body, None),),
                intent_hash=digest,
            )
            return _view(receipt.changes[0], replayed=receipt.replayed)

    def read(self, comparison_id: str) -> ComparisonView:
        key = ResourceKey("comparisons", identifier(comparison_id))
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot()
            saved = next((item for item in records if item.key == key), None)
            if saved is None:
                fail("comparison_missing", "not_found")
            return self._bound_view(saved, records)

    def list(self, *, cursor: str | None = None, limit: int = 50) -> ComparisonPage:
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot()
            stored_by_id = {
                item.key.resource_id: item
                for item in records
                if item.key.collection == "comparisons" and not item.key.scope
            }
            selected, next_cursor = page(tuple(stored_by_id), cursor, limit)
            return ComparisonPage(
                tuple(self._bound_view(stored_by_id[item], records) for item in selected),
                len(stored_by_id),
                next_cursor,
            )


def admit_comparison_from_records(
    stored: StoredRecord, records: tuple[StoredRecord, ...], *, replayed: bool = False
) -> ComparisonView:
    """Admit a captured comparison against its immutable evaluation evidence."""
    saved = _view(stored, replayed=replayed)
    index = {item.key: item for item in records}
    for position, context in enumerate((saved.outcomes.left, saved.outcomes.right)):
        evaluation, frozen = _evaluation(records, index, context.evaluation_id)
        prepared = _prepared(records, frozen)
        try:
            original_context, original_sides = _side(evaluation, frozen, prepared)
        except (MetricsInvalid, ModelInvalid, JsonError):
            fail("invalid_comparison_assessment", "incompatible_data")
        if original_context != context:
            fail("comparison_context_mismatch", "incompatible_data")
        prepared_index = {item.case_id: item for item in prepared}
        for case in saved.outcomes.cases:
            side = case.left if position == 0 else case.right
            if side is not None:
                item = prepared_index[case.case_id]
                if side.request_hash != (
                    item.request.body_hash if item.request is not None else None
                ):
                    fail("comparison_request_link_mismatch", "incompatible_data")
                if side != original_sides[case.case_id]:
                    fail("comparison_assessment_link_mismatch", "incompatible_data")
    return saved
