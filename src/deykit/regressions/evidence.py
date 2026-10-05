"""Strict immutable regression evidence shared by authoring and execution planning."""

from typing import cast

from deykit.application.dataset_support import fail, validated_model
from deykit.contracts.json_value import JsonDocument, JsonValue, semantic_hash
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import CaseRecord, RegressionRecord


def regression_hash(record: RegressionRecord) -> str:
    record = validated_model(RegressionRecord, record, "invalid_regression")
    return semantic_hash(cast(JsonValue, record.model_dump(mode="json", exclude={"content_hash"})))


def frozen_case(record: RegressionRecord) -> CaseRecord:
    """Never substitute a mutable current case for incomplete legacy evidence."""
    record = validated_model(RegressionRecord, record, "invalid_regression")
    case = record.source_case
    if (
        case is None
        or record.decision_id is None
        or record.source_run_id is None
        or record.source_result_snapshot_id is None
        or record.provenance is None
    ):
        fail("legacy_regression_not_executable", "incompatible_data")
    if (
        record.content_hash != regression_hash(record)
        or case.id != record.case_id
        or case.dataset_id != record.dataset_id
        or case.input_source != record.input_source
        or JsonDocument(case.input_source).content_hash != record.input_hash
        or len(set(record.acceptable_option_ids)) != len(record.acceptable_option_ids)
    ):
        fail("regression_evidence_mismatch", "incompatible_data")
    return case


def admit_regression_origin(
    records: tuple[StoredRecord, ...], record: RegressionRecord
) -> CaseRecord:
    """Bind self-contained evidence to its immutable source run and selected result."""
    from deykit.application.evaluations import frozen_evaluation_from_records

    case = frozen_case(record)
    frozen = frozen_evaluation_from_records(
        records,
        record.source_run_id or "",
        record.source_result_snapshot_id or "",
        None,
        "original",
    )
    original = next((c for c in frozen.dataset.cases if c.id == record.case_id), None)
    result = next((r for r in frozen.results.results if r.case_id == record.case_id), None)
    question = frozen.revision.definition.questions[0]
    if (
        original != case
        or result is None
        or result.input_hash != record.input_hash
        or result.attempt_id != record.source_attempt_id
        or frozen.manifest.decision_id != record.decision_id
        or frozen.manifest.dataset_id != record.dataset_id
        or frozen.revision.id != record.decision_revision_id
        or question.id != record.question_id
        or not set(record.acceptable_option_ids).issubset(o.id for o in question.options)
    ):
        fail("regression_origin_mismatch", "incompatible_data")
    return case
