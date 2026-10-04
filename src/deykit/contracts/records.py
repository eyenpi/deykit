"""Version-1 portable records. Domain operations enforce cross-record consistency."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, ValidationInfo, model_validator

from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.json_value import JsonSource, bytes_hash, parse_json
from deykit.contracts.schema import compile_schema


def _utc(value: str) -> str:
    from datetime import datetime

    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value):
        raise ValueError("utc_timestamp_required")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


UtcTimestamp = Annotated[str, AfterValidator(_utc)]


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("blank_text")
    return value


Nonempty = Annotated[str, Field(min_length=1, max_length=100_000), AfterValidator(_not_blank)]
NonnegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class HashedRecord(Record):
    hash_format: Literal["deykit-json-v1"] = "deykit-json-v1"

    @model_validator(mode="after")
    def persisted_hash_format(self, info: ValidationInfo) -> Self:
        if info.context and info.context.get("persisted"):
            if "hash_format" not in self.model_fields_set:
                raise ValueError("missing_hash_format")
        return self


class ProjectRecord(Record):
    id: ResourceId
    name: Nonempty
    created_at: UtcTimestamp
    default_provider_id: ResourceId | None = None


class DecisionRecord(Record):
    id: ResourceId
    name: Nonempty
    archived: bool = False
    latest_revision_id: ResourceId | None = None


class ChoiceOption(FrozenModel):
    id: ResourceId
    name: Nonempty
    description: str | None = None


class ChoiceQuestion(FrozenModel):
    id: ResourceId
    kind: Literal["choice"] = "choice"
    instructions: Nonempty
    options: Annotated[tuple[ChoiceOption, ...], Field(min_length=2)]

    @model_validator(mode="after")
    def unique_options(self) -> Self:
        if len({option.id for option in self.options}) != len(self.options):
            raise ValueError("duplicate_option_id")
        return self


class ChoiceDefinition(Record):
    input_kind: Literal["text", "json"]
    input_schema_source: JsonSource | None = None
    selected_fields: tuple[str, ...] = ()
    questions: Annotated[tuple[ChoiceQuestion, ...], Field(min_length=1, max_length=1)]

    @model_validator(mode="after")
    def valid_input(self) -> Self:
        if len(set(self.selected_fields)) != len(self.selected_fields):
            raise ValueError("duplicate_selected_field")
        if self.input_kind == "text" and self.selected_fields:
            raise ValueError("text_field_selection")
        if self.input_schema_source is not None:
            compile_schema(self.input_schema_source)
        return self


class DecisionDraft(Record):
    """Syntax-invalid/incomplete editor content is saved without claiming it is runnable."""

    decision_id: ResourceId
    editor_source: str
    updated_at: UtcTimestamp
    base_revision_id: ResourceId | None = None


class DecisionRevision(HashedRecord):
    id: ResourceId
    decision_id: ResourceId
    definition: ChoiceDefinition
    content_hash: ContentHash
    created_at: UtcTimestamp
    note: str = ""


class DatasetRecord(Record):
    id: ResourceId
    name: Nonempty
    created_at: UtcTimestamp
    archived: bool = False
    metadata_source: JsonSource = "{}"


class CaseRecord(HashedRecord):
    id: ResourceId
    dataset_id: ResourceId
    input_kind: Literal["text", "json"]
    input_source: JsonSource
    tags: tuple[str, ...] = ()
    split: Literal["development", "calibration", "test"] = "development"
    group_id: ResourceId | None = None
    derived_from: tuple[ResourceId, ...] = ()
    metadata_source: JsonSource = "{}"

    @model_validator(mode="after")
    def input_shape(self) -> Self:
        value = parse_json(self.input_source)
        if not isinstance(value, str if self.input_kind == "text" else dict):
            raise ValueError("invalid_case_input_shape")
        return self


class DatasetSnapshot(HashedRecord):
    id: ResourceId
    dataset_id: ResourceId
    cases: tuple[CaseRecord, ...]
    content_hash: ContentHash
    created_at: UtcTimestamp
    selection_source: JsonSource = "{}"

    @model_validator(mode="after")
    def matching_cases(self) -> Self:
        if any(case.dataset_id != self.dataset_id for case in self.cases):
            raise ValueError("dataset_identity_mismatch")
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate_case_id")
        return self


class LabelRecord(HashedRecord):
    id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    case_id: ResourceId
    question_id: ResourceId
    input_hash: ContentHash
    acceptable_option_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1)]
    status: Literal["active", "disputed"] = "active"
    provenance: Literal["human", "authored_fixture", "imported_unknown", "model_generated"]
    updated_at: UtcTimestamp
    note: str = ""

    @model_validator(mode="after")
    def unique_expectations(self) -> Self:
        if len(set(self.acceptable_option_ids)) != len(self.acceptable_option_ids):
            raise ValueError("duplicate_acceptable_option")
        return self


class LabelChange(Record):
    id: ResourceId
    operation_id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    case_id: ResourceId
    question_id: ResourceId
    action: Literal["set", "clear"]
    label: LabelRecord | None
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def consistent_change(self) -> Self:
        if (self.action == "set") != (self.label is not None):
            raise ValueError("invalid_label_change")
        if self.label is not None and any(
            getattr(self, key) != getattr(self.label, key)
            for key in ("decision_id", "dataset_id", "case_id", "question_id")
        ):
            raise ValueError("label_identity_mismatch")
        return self


class LabelSnapshot(HashedRecord):
    id: ResourceId
    decision_id: ResourceId
    dataset_snapshot_id: ResourceId
    labels: tuple[LabelRecord, ...]
    content_hash: ContentHash
    created_at: UtcTimestamp


class ProviderProfile(Record):
    """Non-secret configuration only; credential references are owned by provider integration."""

    id: ResourceId
    adapter: ResourceId
    requested_model: Nonempty
    destination: Nonempty
    credential_ref: str | None = None


class CompiledRequest(Record):
    adapter: ResourceId
    compiler: ResourceId
    compiler_version: Nonempty
    requested_model: Nonempty
    destination: Nonempty
    body: bytes
    body_hash: ContentHash

    @model_validator(mode="after")
    def exact_body(self) -> Self:
        parse_json(self.body)
        if bytes_hash(self.body) != self.body_hash:
            raise ValueError("request_body_hash_mismatch")
        return self


class NormalizedAnswer(Record):
    question_id: ResourceId
    option_id: ResourceId
    probabilities_source: JsonSource | None = None
    native_confidence_source: JsonSource | None = None
    native_confidence_semantics: str | None = None
    reported_model: str | None = None


class DispatchOutcome(Record):
    """One dispatch, never an implicit retry; unknown cannot be marked retryable."""

    state: Literal["known", "unknown", "not_sent"]
    answer: NormalizedAnswer | None = None
    error: ServiceError | None = None
    retryable: bool = False
    retry_after_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    provider_wide: bool = False
    raw_response_source: JsonSource | None = None
    usage_source: JsonSource | None = None

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if (self.answer is None) == (self.error is None):
            raise ValueError("outcome_requires_answer_or_error")
        if self.answer is not None and (self.state != "known" or self.retryable):
            raise ValueError("invalid_answer_outcome")
        if self.retryable and (self.state != "known" or self.error is None):
            raise ValueError("unknown_never_retryable")
        if self.retry_after_seconds is not None and not self.retryable:
            raise ValueError("retry_delay_without_retry")
        return self


class ExecutionSettings(FrozenModel):
    max_attempts: PositiveInt = 100
    concurrency: PositiveInt = 2
    timeout_seconds: PositiveInt = 60
    deadline_seconds: PositiveInt = 600
    max_retries_per_case: Annotated[int, Field(ge=0, le=1)] = 1


class RunManifest(HashedRecord):
    id: ResourceId
    decision_revision_id: ResourceId
    dataset_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    provider_profile_id: ResourceId
    provider_config_hash: ContentHash
    adapter: ResourceId
    compiler_version: Nonempty
    requested_model: Nonempty
    mode: Literal["fixture", "live"]
    case_ids: tuple[ResourceId, ...]
    settings: ExecutionSettings
    created_at: UtcTimestamp
    operation_id: ResourceId


class RunSegment(Record):
    id: ResourceId
    run_id: ResourceId
    started_at: UtcTimestamp
    deadline_at: UtcTimestamp
    ended_at: UtcTimestamp | None = None
    retry_unknown: bool = False


class RunEvent(Record):
    id: ResourceId
    run_id: ResourceId
    segment_id: ResourceId | None = None
    sequence: NonnegativeInt
    state: Literal[
        "preparing",
        "running",
        "cancelling",
        "cancelled",
        "completed",
        "completed_with_errors",
        "budget_exhausted",
        "interrupted",
        "preflight_failed",
    ]
    created_at: UtcTimestamp
    reason: ServiceError | None = None


class AttemptRecord(Record):
    id: ResourceId
    run_id: ResourceId
    segment_id: ResourceId
    case_id: ResourceId
    number: PositiveInt
    request: CompiledRequest
    reserved_at: UtcTimestamp


class AttemptEvent(Record):
    id: ResourceId
    attempt_id: ResourceId
    sequence: NonnegativeInt
    state: Literal["reserved", "dispatched", "known", "unknown", "not_sent"]
    created_at: UtcTimestamp
    outcome: DispatchOutcome | None = None


class CaseResult(FrozenModel):
    case_id: ResourceId
    input_hash: ContentHash
    status: Literal["pending", "input_invalid", "response_error", "unknown", "valid"]
    attempt_id: ResourceId | None = None
    answer: NormalizedAnswer | None = None
    error: ServiceError | None = None

    @model_validator(mode="after")
    def valid_answer(self) -> Self:
        if (self.status == "valid") != (self.answer is not None):
            raise ValueError("result_answer_status_mismatch")
        if self.status == "valid" and (self.attempt_id is None or self.error is not None):
            raise ValueError("valid_result_requires_attempt")
        return self


class ResultSnapshot(HashedRecord):
    id: ResourceId
    run_id: ResourceId
    results: tuple[CaseResult, ...]
    through_event_sequence: NonnegativeInt
    content_hash: ContentHash
    created_at: UtcTimestamp


class EvaluationRecord(HashedRecord):
    id: ResourceId
    run_id: ResourceId
    result_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    mode: Literal["original", "saved_answer_reevaluation"]
    metrics_source: JsonSource
    content_hash: ContentHash
    created_at: UtcTimestamp


class ComparisonRecord(HashedRecord):
    id: ResourceId
    left_evaluation_id: ResourceId
    right_evaluation_id: ResourceId
    left_result_snapshot_id: ResourceId
    right_result_snapshot_id: ResourceId
    outcomes_source: JsonSource
    content_hash: ContentHash
    created_at: UtcTimestamp


class RegressionRecord(HashedRecord):
    id: ResourceId
    decision_revision_id: ResourceId
    dataset_id: ResourceId
    case_id: ResourceId
    question_id: ResourceId
    input_source: JsonSource
    input_hash: ContentHash
    acceptable_option_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1)]
    reason: Nonempty
    created_at: UtcTimestamp


class ReportRecord(HashedRecord):
    id: ResourceId
    evaluation_ids: tuple[ResourceId, ...]
    result_snapshot_ids: tuple[ResourceId, ...]
    label_snapshot_ids: tuple[ResourceId, ...]
    comparison_id: ResourceId | None = None
    includes_raw_input: bool = False
    content_source: JsonSource
    content_hash: ContentHash
    created_at: UtcTimestamp
