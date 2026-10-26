"""Version-1 portable records. Domain operations enforce cross-record consistency."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, ValidationInfo, model_validator

from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.comparison_json import ComparisonOutcomesSource
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.images import IMAGE_REQUEST_LIMITS, CaseImage
from deykit.contracts.json_value import (
    GENERATED_LIMITS,
    JsonLimits,
    JsonSource,
    bytes_hash,
    parse_json,
)
from deykit.contracts.report_json import ReportContentSource
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
    selected_images: tuple[ResourceId, ...] = Field(default=(), exclude_if=lambda v: not v)
    questions: Annotated[tuple[ChoiceQuestion, ...], Field(min_length=1, max_length=1)]

    @model_validator(mode="after")
    def valid_input(self) -> Self:
        if len(set(self.selected_images)) != len(self.selected_images):
            raise ValueError("duplicate_selected_image")
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
    revision_id: ResourceId | None = None
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
    images: tuple[CaseImage, ...] = Field(default=(), exclude_if=lambda v: not v)

    @model_validator(mode="after")
    def input_shape(self) -> Self:
        if len({image.name for image in self.images}) != len(self.images):
            raise ValueError("duplicate_case_image")
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
    action: Literal["set", "clear", "dispute", "resolve"]
    label: LabelRecord | None
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def consistent_change(self) -> Self:
        if (self.action != "clear") != (self.label is not None):
            raise ValueError("invalid_label_change")
        if self.label is not None and (
            (self.action == "dispute" and self.label.status != "disputed")
            or (self.action == "resolve" and self.label.status != "active")
        ):
            raise ValueError("invalid_label_transition")
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
    semantic_headers_source: JsonSource = Field(default="{}", exclude_if=lambda v: v == "{}")

    body_kind: Literal["json", "image_json"] = Field(
        default="json", exclude_if=lambda v: v == "json"
    )

    @property
    def body_limits(self) -> JsonLimits:
        if self.body_kind == "image_json" or self.semantic_headers_source != "{}":
            return IMAGE_REQUEST_LIMITS
        return GENERATED_LIMITS

    @model_validator(mode="after")
    def exact_body(self) -> Self:
        parse_json(self.body, self.body_limits)
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


class FixtureBinding(Record):
    """One authored outcome for one case and one exact compiled request."""

    id: ResourceId
    case_id: ResourceId
    request: CompiledRequest
    answer: NormalizedAnswer | None = None
    error: ServiceError | None = None

    @model_validator(mode="after")
    def one_outcome(self) -> Self:
        if (self.answer is None) == (self.error is None):
            raise ValueError("fixture_requires_one_outcome")
        return self


class FixtureSet(HashedRecord):
    """Immutable, explicitly authored bindings; every edit creates a new set ID."""

    id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    name: Nonempty
    model_identity: Nonempty
    bindings: Annotated[tuple[FixtureBinding, ...], Field(min_length=1)]
    content_hash: ContentHash
    created_at: UtcTimestamp
    note: str = ""
    evidence_mode: Literal["authored_fixture"] = "authored_fixture"

    @model_validator(mode="after")
    def unique_bindings(self) -> Self:
        if not self.model_identity.startswith("authored-"):
            raise ValueError("authored_model_identity_required")
        if len({binding.id for binding in self.bindings}) != len(self.bindings):
            raise ValueError("duplicate_fixture_binding_id")
        keys = {
            (
                binding.case_id,
                binding.request.compiler,
                binding.request.compiler_version,
                binding.request.body_hash,
            )
            for binding in self.bindings
        }
        if len(keys) != len(self.bindings):
            raise ValueError("duplicate_fixture_request_binding")
        if any(binding.request.requested_model != self.model_identity for binding in self.bindings):
            raise ValueError("fixture_model_mismatch")
        return self


class ExecutionSettings(FrozenModel):
    max_attempts: PositiveInt = 100
    concurrency: PositiveInt = 2
    timeout_seconds: PositiveInt = 60
    deadline_seconds: Annotated[int, Field(ge=1, le=86_400)] = 600
    max_retries_per_case: Annotated[int, Field(ge=0, le=1)] = 1


class RunManifest(HashedRecord):
    id: ResourceId
    execution_group_id: ResourceId | None = None
    regression_ids: tuple[ResourceId, ...] = ()
    baseline_unavailable_reason: Literal["frozen_regression_selection"] | None = None
    option_order: tuple[ResourceId, ...] | None = None
    # Optional only for decoding pre-runner records; executable runs require these.
    decision_id: ResourceId | None = None
    dataset_id: ResourceId | None = None
    baseline_dataset_snapshot_id: ResourceId | None = None
    baseline_label_snapshot_id: ResourceId | None = None
    provider: ProviderProfile | None = None
    fixture_set_id: ResourceId | None = None
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

    @model_validator(mode="after")
    def regression_context(self) -> Self:
        if len(self.regression_ids) != len(set(self.regression_ids)):
            raise ValueError("duplicate_run_regression")
        if bool(self.regression_ids) != (self.baseline_unavailable_reason is not None):
            raise ValueError("invalid_regression_baseline_context")
        return self


class PreparedCase(HashedRecord):
    """Immutable plan entry: exact request or a visible zero-dispatch input error."""

    id: ResourceId
    run_id: ResourceId
    case_id: ResourceId
    input_hash: ContentHash
    request: CompiledRequest | None = None
    error: ServiceError | None = None

    @model_validator(mode="after")
    def exact_plan(self) -> Self:
        if self.id != self.case_id or (self.request is None) == (self.error is None):
            raise ValueError("invalid_prepared_case")
        return self


class RunControl(Record):
    """Append-only caller intent; never mutates the original run settings."""

    id: ResourceId
    run_id: ResourceId
    sequence: PositiveInt
    operation_id: ResourceId
    action: Literal["cancel", "cap_extension"]
    max_attempts: PositiveInt | None = None
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def control_value(self) -> Self:
        if (self.action == "cap_extension") != (self.max_attempts is not None):
            raise ValueError("invalid_run_control")
        return self


class RunSegment(Record):
    id: ResourceId
    run_id: ResourceId
    started_at: UtcTimestamp
    deadline_at: UtcTimestamp
    ended_at: UtcTimestamp | None = None
    retry_unknown: bool = False
    sequence: NonnegativeInt = 0
    cancel_through_sequence: NonnegativeInt = 0


class RunEvent(Record):
    id: ResourceId
    run_id: ResourceId
    segment_id: ResourceId | None = None
    attempt_id: ResourceId | None = None
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
        "attempt_reserved",
        "attempt_dispatched",
        "attempt_settled",
        "cap_extended",
        "segment_ready",
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
    kind: Literal["initial", "rate_retry", "unknown_retry"] = "initial"
    prior_attempt_id: ResourceId | None = None


class AttemptEvent(Record):
    id: ResourceId
    attempt_id: ResourceId
    sequence: NonnegativeInt
    state: Literal["reserved", "dispatched", "known", "unknown", "not_sent"]
    created_at: UtcTimestamp
    outcome: DispatchOutcome | None = None
    duration_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None


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
    execution_operation_id: ResourceId | None = None
    id: ResourceId
    run_id: ResourceId
    result_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    mode: Literal["original", "saved_answer_reevaluation"]
    metrics_source: JsonSource
    content_hash: ContentHash
    created_at: UtcTimestamp


class ResultAnnotation(HashedRecord):
    """Append-only user note against a run/case, never part of model evidence."""

    id: ResourceId
    run_id: ResourceId
    case_id: ResourceId
    operation_id: ResourceId
    note: Nonempty
    content_hash: ContentHash
    created_at: UtcTimestamp


class ComparisonRecord(HashedRecord):
    id: ResourceId
    left_evaluation_id: ResourceId
    right_evaluation_id: ResourceId
    left_result_snapshot_id: ResourceId
    right_result_snapshot_id: ResourceId
    outcomes_source: ComparisonOutcomesSource
    content_hash: ContentHash
    created_at: UtcTimestamp


class RegressionRecord(HashedRecord):
    id: ResourceId
    content_hash: ContentHash | None = None
    # Legacy records remain readable; execution requires this full immutable evidence.
    decision_id: ResourceId | None = None
    source_run_id: ResourceId | None = None
    source_result_snapshot_id: ResourceId | None = None
    source_attempt_id: ResourceId | None = None
    source_case: CaseRecord | None = None
    provenance: (
        Literal["human", "authored_fixture", "imported_unknown", "model_generated"] | None
    ) = None
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
    includes_raw_request: bool = False
    includes_raw_response: bool = False
    diagnostic_snapshot_id: ResourceId | None = None
    check_snapshot_id: ResourceId | None = None
    content_source: ReportContentSource
    content_hash: ContentHash
    created_at: UtcTimestamp
