"""Strict portable report values and detached application views."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from deykit.comparisons.models import ComparisonOutcomes
from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.images import SelectedImage
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.records import NonnegativeInt, ReportRecord, UtcTimestamp

ReportFormat = Literal["json", "markdown", "csv"]
ReportTargetKind = Literal["run", "evaluation", "comparison", "diagnostic", "check"]
ClassificationPolicy = Literal[
    "classification-strict-v1",
    "classification-strict-v2",
    "classification-strict-v3",
    "classification-strict-v4",
]


class RawChoices(FrozenModel):
    inputs: bool = False
    requests: bool = False
    responses: bool = False


class TokenPrice(FrozenModel):
    adapter: ResourceId
    requested_model: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    input_per_million: str = Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,12})?$")
    output_per_million: str = Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,12})?$")
    source: str = Field(min_length=1, max_length=500)
    as_of: UtcTimestamp


class ClassificationPricing(FrozenModel):
    rates: tuple[TokenPrice, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def unique_models(self) -> ClassificationPricing:
        keys = tuple((rate.adapter, rate.requested_model) for rate in self.rates)
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate_token_price")
        return self


class ReportRequest(FrozenModel):
    target_id: ResourceId
    target_kind: ReportTargetKind | None = None
    evaluation_id: ResourceId | None = None
    result_snapshot_id: ResourceId | None = None
    group_snapshot_id: ResourceId | None = None
    raw: RawChoices = Field(default_factory=RawChoices)
    preset: Literal["classification"] | None = None
    pricing: ClassificationPricing | None = None
    category_only: bool = False

    @model_validator(mode="after")
    def selector_matches_kind(self) -> ReportRequest:
        if self.pricing is not None and self.preset is None:
            raise ValueError("pricing_requires_classification")
        if self.category_only and self.preset is None:
            raise ValueError("category_only_requires_classification")
        if self.preset is not None and self.target_kind in ("diagnostic", "check"):
            raise ValueError("invalid_classification_target")
        if self.target_kind in ("diagnostic", "check"):
            if self.evaluation_id is not None or self.result_snapshot_id is not None:
                raise ValueError("invalid_report_selector")
        elif self.group_snapshot_id is not None:
            raise ValueError("invalid_report_selector")
        return self


class FrozenTarget(FrozenModel):
    kind: ReportTargetKind
    target_id: ResourceId
    evaluation_ids: tuple[ResourceId, ...] = ()
    result_snapshot_ids: tuple[ResourceId, ...] = ()
    label_snapshot_ids: tuple[ResourceId, ...] = ()
    comparison_id: ResourceId | None = None
    comparison_hash: ContentHash | None = None
    group_snapshot_id: ResourceId | None = None

    @model_validator(mode="after")
    def selector_matches_kind(self) -> FrozenTarget:
        if self.kind in ("diagnostic", "check"):
            if (
                self.group_snapshot_id is None
                or self.evaluation_ids
                or self.comparison_id is not None
            ):
                raise ValueError("invalid_report_group_target")
            if self.comparison_hash is not None:
                raise ValueError("invalid_report_group_target")
            return self
        if self.group_snapshot_id is not None:
            raise ValueError("invalid_report_selector")
        if self.kind == "comparison":
            if self.comparison_id is None or self.comparison_hash is None:
                raise ValueError("invalid_report_comparison_target")
        elif self.comparison_id is not None or self.comparison_hash is not None:
            raise ValueError("invalid_report_comparison_target")
        return self


class RawMaterial(FrozenModel):
    category: Literal["input", "request", "response"]
    run_id: ResourceId
    case_id: ResourceId
    attempt_id: ResourceId | None = None
    encoding: Literal["json_source_utf8", "utf8", "base64"] | None = None
    source: str | None = None
    identity_kind: Literal[
        "input_semantic_hash",
        "prepared_request_bytes_hash",
        "stored_response_utf8_hash",
        "stored_response_bytes_hash",
    ]
    original_hash: ContentHash | None = None
    sanitized_hash: ContentHash | None = None
    changed_by_redaction: bool = False
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def source_state(self) -> RawMaterial:
        if (self.source is None) != (self.encoding is None):
            raise ValueError("invalid_raw_material_source")
        if self.source is None and not self.unavailable_reason:
            raise ValueError("missing_raw_material_reason")
        if self.source is None and (
            self.original_hash is not None or self.sanitized_hash is not None
        ):
            raise ValueError("raw_material_unavailable_hash")
        if self.source is not None and self.unavailable_reason is not None:
            raise ValueError("raw_material_source_with_reason")
        expected_identity = {
            "input": "input_semantic_hash",
            "request": "prepared_request_bytes_hash",
            "response": self.identity_kind,
        }[self.category]
        if self.category != "response" and self.identity_kind != expected_identity:
            raise ValueError("raw_material_identity_mismatch")
        if self.category == "response" and self.identity_kind not in {
            "stored_response_utf8_hash",
            "stored_response_bytes_hash",
        }:
            raise ValueError("raw_material_identity_mismatch")
        if self.source is not None:
            if self.original_hash is None or self.sanitized_hash is None:
                raise ValueError("raw_material_hash_missing")
            if self.encoding == "base64":
                try:
                    decoded = base64.b64decode(self.source, validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError("invalid_raw_evidence") from None
                if base64.b64encode(decoded).decode("ascii") != self.source:
                    raise ValueError("invalid_raw_evidence")
                if bytes_hash(decoded) != self.sanitized_hash:
                    raise ValueError("invalid_raw_evidence")
            elif bytes_hash(self.source.encode("utf-8", "strict")) != self.sanitized_hash:
                raise ValueError("invalid_raw_evidence")
        return self


class RateDisplay(FrozenModel):
    numerator: NonnegativeInt
    denominator: NonnegativeInt
    value: str | None
    reason: str | None

    @model_validator(mode="after")
    def has_value_or_reason(self) -> RateDisplay:
        if self.denominator > 0:
            if self.value is None or self.reason is not None or self.numerator > self.denominator:
                raise ValueError("invalid_report_rate")
        elif self.value is not None or not self.reason:
            raise ValueError("invalid_report_rate")
        return self


class StatusCounts(FrozenModel):
    pending: NonnegativeInt
    input_invalid: NonnegativeInt
    response_error: NonnegativeInt
    unknown: NonnegativeInt
    valid: NonnegativeInt


class ClassMetricDisplay(FrozenModel):
    option_id: ResourceId
    support: NonnegativeInt
    predicted: NonnegativeInt
    true_positive: NonnegativeInt
    precision: RateDisplay
    recall: RateDisplay
    f1: RateDisplay


class EvaluationSummaryDisplay(FrozenModel):
    selected_count: NonnegativeInt
    status_counts: StatusCounts
    coverage: RateDisplay
    set_accuracy: RateDisplay
    eligible_set_count: NonnegativeInt
    correct_set_count: NonnegativeInt
    single_label_count: NonnegativeInt
    unlabelled_valid_count: NonnegativeInt
    exclusion_counts: dict[str, NonnegativeInt]
    option_ids: tuple[ResourceId, ...]
    confusion_matrix: tuple[tuple[NonnegativeInt, ...], ...]
    classes: tuple[ClassMetricDisplay, ...]
    macro_f1: RateDisplay
    macro_f1_class_count: NonnegativeInt
    native_confidence_present_count: NonnegativeInt
    native_confidence_mean: RateDisplay


class BaselineDisplay(FrozenModel):
    option_id: ResourceId | None
    fit_support: NonnegativeInt
    fit_excluded_acceptable_sets: NonnegativeInt
    fit_dataset_snapshot_id: ResourceId
    fit_label_snapshot_id: ResourceId
    evaluation_dataset_snapshot_id: ResourceId
    evaluation_label_snapshot_id: ResourceId
    evaluation_splits: tuple[Literal["development", "calibration", "test"], ...]
    overlap_case_ids: tuple[ResourceId, ...]
    selected_count: NonnegativeInt
    paired_count: NonnegativeInt
    scoring_population: Literal["provider_valid_applicable_labels"]
    scored_count: NonnegativeInt
    accuracy: RateDisplay
    unavailable_reason: str | None


class LatencyDisplay(FrozenModel):
    mode: Literal["live", "fixture"]
    sample_count: NonnegativeInt
    p50_seconds: str | None
    p95_seconds: str | None
    reason: str | None
    method: Literal["nearest_rank"]


class UsageDisplay(FrozenModel):
    mode: Literal["live", "fixture"]
    dispatched_attempt_count: NonnegativeInt
    reported_attempt_count: NonnegativeInt
    reported_input_tokens: NonnegativeInt | None
    reported_output_tokens: NonnegativeInt | None
    total_input_tokens: NonnegativeInt | None
    total_output_tokens: NonnegativeInt | None
    source_kind: str | None
    reported_at: UtcTimestamp | None
    reason: str | None
    cost: None
    cost_reason: Literal["pricing_source_unavailable"]


class EvaluationMetrics(Record):
    profile: Literal["deykit-evaluation-v1"]
    run_id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    decision_revision_id: ResourceId
    dataset_snapshot_id: ResourceId
    result_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    evaluation_mode: Literal["original", "saved_answer_reevaluation"]
    evidence_mode: Literal["fixture", "live"]
    summary: EvaluationSummaryDisplay
    baseline: BaselineDisplay
    latency: LatencyDisplay
    usage: UsageDisplay


class CohortSelection(FrozenModel):
    split: Literal["all", "development", "calibration", "test"] | None
    explicit_case_ids: bool | None
    requested_case_count: NonnegativeInt | None
    regression_selected: bool


class RunEvidenceContext(FrozenModel):
    run_id: ResourceId
    manifest_hash: ContentHash
    decision_id: ResourceId
    decision_revision_id: ResourceId
    definition_hash: ContentHash
    dataset_id: ResourceId
    dataset_snapshot_id: ResourceId
    dataset_hash: ContentHash
    label_snapshot_id: ResourceId
    label_hash: ContentHash
    result_snapshot_id: ResourceId
    result_hash: ContentHash
    through_event_sequence: NonnegativeInt
    evaluation_id: ResourceId
    evaluation_hash: ContentHash
    evaluation_mode: Literal["original", "saved_answer_reevaluation"]
    evidence_mode: Literal["fixture", "live"]
    fixture_set_id: ResourceId | None
    provider_profile_id: ResourceId
    provider_config_hash: ContentHash
    adapter: ResourceId
    compiler_ids: tuple[ResourceId, ...]
    compiler_version: str
    requested_model: str
    answering_models: tuple[str, ...]
    question_id: ResourceId
    option_ids: tuple[ResourceId, ...]
    option_order: tuple[ResourceId, ...]
    selected_case_ids: tuple[ResourceId, ...]
    cohort_selection: CohortSelection | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    baseline_dataset_snapshot_id: ResourceId
    baseline_dataset_hash: ContentHash
    baseline_label_snapshot_id: ResourceId
    baseline_label_hash: ContentHash

    @model_validator(mode="after")
    def consistent_order(self) -> RunEvidenceContext:
        if (
            len(set(self.compiler_ids)) != len(self.compiler_ids)
            or tuple(sorted(self.compiler_ids)) != self.compiler_ids
            or len(set(self.answering_models)) != len(self.answering_models)
            or tuple(sorted(self.answering_models)) != self.answering_models
            or len(set(self.option_ids)) != len(self.option_ids)
            or len(set(self.option_order)) != len(self.option_order)
            or set(self.option_ids) != set(self.option_order)
            or len(set(self.selected_case_ids)) != len(self.selected_case_ids)
        ):
            raise ValueError("invalid_report_context")
        return self


class ReportCase(FrozenModel):
    case_id: ResourceId
    input_hash: ContentHash
    selected_images: tuple[SelectedImage, ...] = Field(default=(), exclude_if=lambda v: not v)
    category_only_option_id: ResourceId | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    split: Literal["development", "calibration", "test"]
    status: Literal["pending", "input_invalid", "response_error", "unknown", "valid"]
    attempt_id: ResourceId | None
    answer_question_id: ResourceId | None
    answer_option_id: ResourceId | None
    probabilities_source: str | None
    native_confidence_source: str | None
    native_confidence_semantics: str | None
    reported_model: str | None
    expected_option_ids: tuple[ResourceId, ...]
    label_provenance: str | None
    correct: bool | None
    single_label_class: bool
    exclusion_reasons: tuple[str, ...]
    legacy_question_ids: tuple[ResourceId, ...]
    legacy_expected_option_ids: tuple[tuple[ResourceId, ...], ...]
    legacy_label_provenances: tuple[str, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    legacy_exclusion_reasons: tuple[tuple[str, ...], ...]
    error: ServiceError | None


class AttemptEvidence(FrozenModel):
    run_id: ResourceId
    case_id: ResourceId
    attempt_id: ResourceId
    number: NonnegativeInt
    kind: Literal["initial", "rate_retry", "unknown_retry"]
    prior_attempt_id: ResourceId | None
    compiler: ResourceId
    adapter: ResourceId
    compiler_version: str
    requested_model: str
    body_hash: ContentHash
    state: Literal["reserved", "dispatched", "known", "unknown", "not_sent"]
    duration_seconds: str | None
    error: ServiceError | None
    response_stored: bool
    usage_stored: bool


class ReportEvaluation(FrozenModel):
    context: RunEvidenceContext
    metrics: EvaluationMetrics
    cases: tuple[ReportCase, ...]
    attempts: tuple[AttemptEvidence, ...]

    @model_validator(mode="after")
    def links_match(self) -> ReportEvaluation:
        if (
            self.context.run_id != self.metrics.run_id
            or self.context.decision_id != self.metrics.decision_id
            or self.context.dataset_id != self.metrics.dataset_id
            or self.context.decision_revision_id != self.metrics.decision_revision_id
            or self.context.dataset_snapshot_id != self.metrics.dataset_snapshot_id
            or self.context.result_snapshot_id != self.metrics.result_snapshot_id
            or self.context.label_snapshot_id != self.metrics.label_snapshot_id
            or self.context.evaluation_mode != self.metrics.evaluation_mode
            or self.context.evidence_mode != self.metrics.evidence_mode
        ):
            raise ValueError("invalid_report_evaluation")
        if tuple(item.case_id for item in self.cases) != self.context.selected_case_ids:
            raise ValueError("invalid_report_case_order")
        if any(item.run_id != self.context.run_id for item in self.attempts):
            raise ValueError("invalid_report_attempt_run")
        return self


class CategoryOnlyCase(FrozenModel):
    source: Literal["valid", "salvaged", "unavailable"]
    option_id: ResourceId | None
    correct: bool | None


class ClassificationCase(FrozenModel):
    case_id: ResourceId
    applicable: bool
    strict_correct: bool | None
    category_only: CategoryOnlyCase | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class TokenListCost(FrozenModel):
    price: TokenPrice | None
    reported_subtotal: str | None
    total: str | None
    unknown_attempt_count: NonnegativeInt
    reason: str | None
    interpretation: Literal["token_list_estimate_not_billed"] = "token_list_estimate_not_billed"


class CategoryOnlySummary(FrozenModel):
    salvaged_count: NonnegativeInt
    usable_count: NonnegativeInt
    full_cohort_accuracy: RateDisplay
    usable_accuracy: RateDisplay


class ClassificationEvaluation(FrozenModel):
    evaluation_id: ResourceId
    selected_count: NonnegativeInt
    applicable_count: NonnegativeInt
    excluded_count: NonnegativeInt
    full_cohort_strict_accuracy: RateDisplay
    valid_answer_accuracy: RateDisplay
    applicable_status_counts: StatusCounts
    failed_count: NonnegativeInt
    missing_count: NonnegativeInt
    refused_count: NonnegativeInt | None = None
    refusal_reason: Literal[
        "distinct_refusal_status_not_recorded", "explicit_provider_refusals_only"
    ] = "distinct_refusal_status_not_recorded"
    class_population: Literal["applicable_single_labels_including_failures"] = (
        "applicable_single_labels_including_failures"
    )
    class_count: NonnegativeInt
    classes: tuple[ClassMetricDisplay, ...]
    cases: tuple[ClassificationCase, ...]
    cost: TokenListCost
    category_only: CategoryOnlySummary | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


ExperimentalPairBucket = Literal[
    "left_only",
    "right_only",
    "changed_question_options",
    "changed_expectations",
    "unavailable_answer",
    "excluded_expectation",
    "both_correct",
    "improved",
    "regressed",
    "both_wrong",
]


class SelectedInputDifference(FrozenModel):
    changed: bool | None
    unavailable_reason: Literal["case_missing", "input_not_prepared"] | None


class ExperimentalPairCase(FrozenModel):
    case_id: ResourceId
    bucket: ExperimentalPairBucket
    input_identity_changed: bool | None
    request_bytes_changed: bool | None
    image_presence_changed: bool | None
    selected_image_names_changed: bool | None
    image_source_changed: bool | None
    prepared_image_changed: bool | None
    preparation_changed: bool | None
    selected_input: SelectedInputDifference | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class ExperimentalComparison(FrozenModel):
    policy: Literal["matching_labels_allow_changed_inputs_v1"]
    selected_input_comparison: Literal["not_recorded", "reconstructed_selection_v1"]
    counts: dict[ExperimentalPairBucket, NonnegativeInt]
    quality_denominator: NonnegativeInt
    left_correct_count: NonnegativeInt
    right_correct_count: NonnegativeInt
    paired_case_count: NonnegativeInt
    input_identity_changed_count: NonnegativeInt
    request_bytes_changed_count: NonnegativeInt
    request_bytes_unavailable_count: NonnegativeInt
    image_presence_changed_count: NonnegativeInt
    selected_image_names_changed_count: NonnegativeInt
    image_source_changed_count: NonnegativeInt
    prepared_image_changed_count: NonnegativeInt
    preparation_changed_count: NonnegativeInt
    selected_input_changed_count: NonnegativeInt | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    selected_input_unavailable_count: NonnegativeInt | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    definition_changed: bool
    adapter_changed: bool
    requested_model_changed: bool | None
    provider_config_changed: bool
    cases: tuple[ExperimentalPairCase, ...]


class ClassificationReport(FrozenModel):
    policy: ClassificationPolicy = "classification-strict-v1"
    pricing: ClassificationPricing = Field(default_factory=ClassificationPricing)
    evaluations: tuple[ClassificationEvaluation, ...]
    comparison_policy: Literal["compatible_pairs_only"] = "compatible_pairs_only"
    category_only_scoring: Literal["disabled", "jev_probability_only_v1"] = "disabled"
    experimental_comparison: ExperimentalComparison | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    latency_population: Literal["all_recorded_live_dispatch_durations_including_retries"] = (
        "all_recorded_live_dispatch_durations_including_retries"
    )
    treatment_limitations: tuple[str, ...] = (
        "cohort_selection_does_not_establish_representativeness",
        "input_hash_compares_selected_json_only",
        "modality_and_preprocessing_not_independently_recorded",
        "compatible_pairs_do_not_establish_model_only_causality",
    )


class CaseImageTreatment(FrozenModel):
    case_id: ResourceId
    selected_images: tuple[SelectedImage, ...]


class MemberEvidenceContext(FrozenModel):
    """Pinned run context for a group member, with no P10 evaluation identity."""

    run_id: ResourceId
    manifest_hash: ContentHash
    decision_id: ResourceId
    decision_revision_id: ResourceId
    definition_hash: ContentHash
    dataset_id: ResourceId
    dataset_snapshot_id: ResourceId
    dataset_hash: ContentHash
    label_snapshot_id: ResourceId
    label_hash: ContentHash
    result_snapshot_id: ResourceId
    result_hash: ContentHash
    through_event_sequence: NonnegativeInt
    evidence_mode: Literal["fixture", "live"]
    fixture_set_id: ResourceId | None
    provider_profile_id: ResourceId
    provider_config_hash: ContentHash
    adapter: ResourceId
    compiler_ids: tuple[ResourceId, ...]
    compiler_version: str
    requested_model: str
    answering_models: tuple[str, ...]
    question_id: ResourceId
    option_ids: tuple[ResourceId, ...]
    option_order: tuple[ResourceId, ...]
    selected_case_ids: tuple[ResourceId, ...]
    image_treatments: tuple[CaseImageTreatment, ...] = Field(default=(), exclude_if=lambda v: not v)
    baseline_dataset_snapshot_id: ResourceId
    baseline_dataset_hash: ContentHash
    baseline_label_snapshot_id: ResourceId
    baseline_label_hash: ContentHash

    @model_validator(mode="after")
    def consistent_order(self) -> MemberEvidenceContext:
        if (
            len(set(self.compiler_ids)) != len(self.compiler_ids)
            or tuple(sorted(self.compiler_ids)) != self.compiler_ids
            or len(set(self.answering_models)) != len(self.answering_models)
            or tuple(sorted(self.answering_models)) != self.answering_models
            or len(set(self.option_ids)) != len(self.option_ids)
            or len(set(self.option_order)) != len(self.option_order)
            or set(self.option_ids) != set(self.option_order)
            or len(set(self.selected_case_ids)) != len(self.selected_case_ids)
        ):
            raise ValueError("invalid_report_context")
        return self


class DiagnosticCaseDisplay(FrozenModel):
    case_id: ResourceId
    option_ids: tuple[ResourceId | None, ...]
    statuses: tuple[str, ...]
    observed_disagreement: bool
    fully_observed: bool


class DiagnosticOrderAccuracyDisplay(FrozenModel):
    option_order: tuple[ResourceId, ...]
    accuracy: RateDisplay
    accuracy_exclusions: dict[str, NonnegativeInt]
    accuracy_label_provenance: dict[str, NonnegativeInt]
    common_accuracy: RateDisplay
    flips_from_original: RateDisplay


class DiagnosticCaseFlipsDisplay(FrozenModel):
    case_id: ResourceId
    flipped_from_original: tuple[bool | None, ...]
    flip_rate: RateDisplay


class DiagnosticOrderAnalysisDisplay(FrozenModel):
    orders: tuple[DiagnosticOrderAccuracyDisplay, ...]
    accuracy_gap: RateDisplay
    common_accuracy_gap: RateDisplay
    cases: tuple[DiagnosticCaseFlipsDisplay, ...]


class DiagnosticSummaryDisplay(FrozenModel):
    independent_case_count: NonnegativeInt
    order_count: NonnegativeInt
    expanded_result_count: NonnegativeInt
    fully_observed_case_count: NonnegativeInt
    disagreement: RateDisplay
    cases: tuple[DiagnosticCaseDisplay, ...]
    interpretation: Literal["observed_request_order_sensitivity"]
    order_analysis: DiagnosticOrderAnalysisDisplay | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class GroupReportContext(FrozenModel):
    group_id: ResourceId
    group_hash: ContentHash
    group_kind: Literal["choice_order", "regression_check"]
    max_attempts: NonnegativeInt
    deadline_seconds: NonnegativeInt
    snapshot_id: ResourceId
    snapshot_hash: ContentHash
    snapshot_sequence: NonnegativeInt
    segment_id: ResourceId | None
    members: tuple[MemberEvidenceContext, ...]


class DiagnosticReport(GroupReportContext):
    group_kind: Literal["choice_order"]
    seed: int
    algorithm: str
    orders: tuple[tuple[ResourceId, ...], ...]
    summary: DiagnosticSummaryDisplay


class CheckCaseDisplay(FrozenModel):
    regression_id: ResourceId
    regression_hash: ContentHash
    dataset_id: ResourceId
    case_id: ResourceId
    run_id: ResourceId
    result_snapshot_id: ResourceId
    status: str
    expected_option_ids: tuple[ResourceId, ...]
    actual_option_id: ResourceId | None
    passed: bool | None
    provenance: str
    original_split: Literal["development", "calibration", "test"]
    input_hash: ContentHash
    source_run_id: ResourceId | None
    source_result_snapshot_id: ResourceId | None
    source_attempt_id: ResourceId | None
    reason: str


class CheckReport(GroupReportContext):
    group_kind: Literal["regression_check"]
    cases: tuple[CheckCaseDisplay, ...]
    expectation_failures: NonnegativeInt
    baseline_unavailable: Literal["frozen_regression_selection"]


class ReportContent(Record):
    profile: Literal["deykit-report-v1"] = "deykit-report-v1"
    target: FrozenTarget
    raw: RawChoices = Field(default_factory=RawChoices)
    evaluations: tuple[ReportEvaluation, ...] = ()
    comparison: ComparisonOutcomes | None = None
    diagnostic: DiagnosticReport | None = None
    check: CheckReport | None = None
    raw_material: tuple[RawMaterial, ...] = ()
    limitations: tuple[str, ...] = ()
    classification: ClassificationReport | None = None

    @model_validator(mode="after")
    def branch_matches_target(self) -> ReportContent:
        if self.classification is not None:
            classification = self.classification
            if self.target.kind not in ("run", "evaluation", "comparison") or tuple(
                item.evaluation_id for item in classification.evaluations
            ) != tuple(item.context.evaluation_id for item in self.evaluations):
                raise ValueError("invalid_classification_target")
            if classification.policy == "classification-strict-v3":
                if (
                    self.target.kind != "comparison"
                    or classification.experimental_comparison is None
                ):
                    raise ValueError("invalid_experimental_comparison")
            elif classification.policy == "classification-strict-v4":
                if (self.target.kind == "comparison") != (
                    classification.experimental_comparison is not None
                ):
                    raise ValueError("invalid_experimental_comparison")
            elif classification.experimental_comparison is not None:
                raise ValueError("invalid_experimental_comparison")
            is_v4 = classification.policy == "classification-strict-v4"
            category_only = classification.category_only_scoring != "disabled"
            if category_only and not is_v4:
                raise ValueError("invalid_category_only_policy")
            for evaluation, summary in zip(
                self.evaluations, classification.evaluations, strict=True
            ):
                if (evaluation.context.cohort_selection is not None) != is_v4:
                    raise ValueError("invalid_cohort_selection_projection")
                if any(
                    len(case.legacy_label_provenances)
                    != (len(case.legacy_question_ids) if is_v4 else 0)
                    for case in evaluation.cases
                ):
                    raise ValueError("invalid_legacy_provenance_projection")
                if not category_only and any(
                    case.category_only_option_id is not None for case in evaluation.cases
                ):
                    raise ValueError("invalid_category_only_projection")
                if (summary.category_only is not None) != category_only or any(
                    (case.category_only is not None) != category_only for case in summary.cases
                ):
                    raise ValueError("invalid_category_only_projection")
            experimental = classification.experimental_comparison
            if experimental is not None and (
                (experimental.selected_input_comparison == "reconstructed_selection_v1") != is_v4
                or any((case.selected_input is not None) != is_v4 for case in experimental.cases)
            ):
                raise ValueError("invalid_selected_input_projection")
        if self.target.kind in ("run", "evaluation"):
            if len(self.evaluations) != 1 or self.comparison is not None:
                raise ValueError("invalid_report_target_branch")
            if self.diagnostic is not None or self.check is not None:
                raise ValueError("invalid_report_target_branch")
        elif self.target.kind == "comparison":
            if len(self.evaluations) != 2 or self.comparison is None:
                raise ValueError("invalid_report_target_branch")
            if self.diagnostic is not None or self.check is not None:
                raise ValueError("invalid_report_target_branch")
        elif self.target.kind == "diagnostic":
            if (
                self.evaluations
                or self.comparison is not None
                or self.diagnostic is None
                or self.check is not None
            ):
                raise ValueError("invalid_report_target_branch")
        elif (
            self.evaluations
            or self.comparison is not None
            or self.check is None
            or self.diagnostic is not None
        ):
            raise ValueError("invalid_report_target_branch")
        selected = {
            name
            for name, enabled in (
                ("input", self.raw.inputs),
                ("request", self.raw.requests),
                ("response", self.raw.responses),
            )
            if enabled
        }
        if any(item.category not in selected for item in self.raw_material):
            raise ValueError("raw_material_flag_mismatch")
        evidence_contexts = tuple(item.context for item in self.evaluations)
        group_context = self.diagnostic or self.check
        member_contexts = group_context.members if group_context is not None else ()
        expected_eval_ids = tuple(dict.fromkeys(item.evaluation_id for item in evidence_contexts))
        expected_result_ids = (
            tuple(dict.fromkeys(item.result_snapshot_id for item in evidence_contexts))
            if evidence_contexts
            else tuple(dict.fromkeys(item.result_snapshot_id for item in member_contexts))
        )
        expected_label_ids = (
            tuple(dict.fromkeys(item.label_snapshot_id for item in evidence_contexts))
            if evidence_contexts
            else tuple(dict.fromkeys(item.label_snapshot_id for item in member_contexts))
        )
        if (
            self.target.evaluation_ids != expected_eval_ids
            or self.target.result_snapshot_ids != expected_result_ids
            or self.target.label_snapshot_ids != expected_label_ids
        ):
            raise ValueError("report_target_links_mismatch")
        if self.target.kind == "run" and any(
            item.context.run_id != self.target.target_id for item in self.evaluations
        ):
            raise ValueError("report_run_target_mismatch")
        if self.target.kind == "evaluation" and (
            len(self.evaluations) != 1
            or self.evaluations[0].context.evaluation_id != self.target.target_id
        ):
            raise ValueError("report_evaluation_target_mismatch")
        if self.target.kind == "comparison":
            assert self.comparison is not None
            if self.target.comparison_id != self.target.target_id or (
                self.comparison.left.evaluation_id,
                self.comparison.right.evaluation_id,
            ) != tuple(item.context.evaluation_id for item in self.evaluations):
                raise ValueError("report_comparison_links_mismatch")
        if self.target.kind in ("diagnostic", "check"):
            assert group_context is not None
            if (
                group_context.group_id != self.target.target_id
                or group_context.snapshot_id != self.target.group_snapshot_id
            ):
                raise ValueError("report_group_links_mismatch")
        allowed_limitations = {
            "authored_fixture_not_provider_quality",
            "saved_answers_no_fresh_inference",
            "partial_results",
            "native_confidence_not_calibrated",
            "pricing_source_unavailable",
            "baseline_overlap",
            "raw_material_sanitized",
            "unknown_plaintext_secrets_not_recognized",
            "observed_request_order_sensitivity",
            "frozen_regression_selection",
        }
        if len(set(self.limitations)) != len(self.limitations) or any(
            item not in allowed_limitations for item in self.limitations
        ):
            raise ValueError("invalid_report_limitations")
        return self


@dataclass(frozen=True)
class ReportView:
    record: ReportRecord
    etag: str
    content: ReportContent
    replayed: bool = False


@dataclass(frozen=True)
class ReportPage:
    items: tuple[ReportMetadata, ...]
    total: int
    next_cursor: str | None


class ReportMetadata(FrozenModel):
    report_id: ResourceId
    content_hash: ContentHash
    created_at: UtcTimestamp
    target_id: ResourceId | None = None
    target_kind: ReportTargetKind | None = None
    raw: RawChoices = Field(default_factory=RawChoices)
    evaluation_ids: tuple[ResourceId, ...] = ()
    result_snapshot_ids: tuple[ResourceId, ...] = ()
    label_snapshot_ids: tuple[ResourceId, ...] = ()
    comparison_id: ResourceId | None = None
    diagnostic_snapshot_id: ResourceId | None = None
    check_snapshot_id: ResourceId | None = None
    evidence_modes: tuple[str, ...] = ()
    legacy: bool = False
    nonexportable_reason: str | None = None


@dataclass(frozen=True)
class RenderedArtifact:
    report_id: str
    format: ReportFormat
    body: bytes
    bytes_hash: str
    byte_count: int


class ExportOutcome(FrozenModel):
    report: ReportMetadata
    format: ReportFormat
    success: bool
    destination: str | None
    requested_destination: str | None
    artifact_hash: ContentHash
    byte_count: int = Field(ge=0)
    error: ServiceError | None = None
    durability_warning: ServiceError | None = None

    @model_validator(mode="after")
    def consistent_outcome(self) -> ExportOutcome:
        if self.success != (self.destination is not None and self.error is None):
            raise ValueError("invalid_export_outcome")
        if not self.success and self.durability_warning is not None:
            raise ValueError("invalid_export_outcome")
        return self


ReportContent.model_rebuild(_types_namespace={"Decimal": Decimal})
