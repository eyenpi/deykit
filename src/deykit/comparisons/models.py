"""Versioned comparison evidence; no mutable source or transport dependencies."""

from typing import Literal, Self

from pydantic import Field, model_validator

from deykit.comparisons.rules import classify
from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.identities import ContentHash, ResourceId

Status = Literal["pending", "input_invalid", "response_error", "unknown", "valid"]
Bucket = Literal[
    "left_only",
    "right_only",
    "changed_input",
    "changed_question_options",
    "changed_expectations",
    "unavailable_answer",
    "excluded_expectation",
    "unlabelled_agreement",
    "unlabelled_disagreement",
    "both_correct",
    "improved",
    "regressed",
    "both_wrong",
]
BUCKETS: tuple[Bucket, ...] = (
    "left_only",
    "right_only",
    "changed_input",
    "changed_question_options",
    "changed_expectations",
    "unavailable_answer",
    "excluded_expectation",
    "unlabelled_agreement",
    "unlabelled_disagreement",
    "both_correct",
    "improved",
    "regressed",
    "both_wrong",
)
STATUSES: tuple[Status, ...] = ("pending", "input_invalid", "response_error", "unknown", "valid")


class ComparisonContext(FrozenModel):
    evaluation_id: ResourceId
    evaluation_hash: ContentHash
    evaluation_mode: Literal["original", "saved_answer_reevaluation"]
    run_id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    decision_revision_id: ResourceId
    definition_hash: ContentHash
    dataset_snapshot_id: ResourceId
    dataset_hash: ContentHash
    label_snapshot_id: ResourceId
    label_hash: ContentHash
    result_snapshot_id: ResourceId
    result_hash: ContentHash
    evidence_mode: Literal["fixture", "live"]
    adapter: ResourceId
    compiler_ids: tuple[ResourceId, ...]
    compiler_version: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    answering_models: tuple[str, ...]
    provider_profile_id: ResourceId
    provider_config_hash: ContentHash
    question_id: ResourceId
    option_ids: tuple[ResourceId, ...]
    option_order: tuple[ResourceId, ...]
    selected_case_ids: tuple[ResourceId, ...]

    @model_validator(mode="after")
    def unique_context(self) -> Self:
        if (
            not self.option_ids
            or len(set(self.option_ids)) != len(self.option_ids)
            or len(set(self.option_order)) != len(self.option_order)
            or set(self.option_order) != set(self.option_ids)
            or len(set(self.selected_case_ids)) != len(self.selected_case_ids)
            or any(not item for item in self.answering_models)
            or tuple(sorted(set(self.answering_models))) != self.answering_models
            or any(not item for item in self.compiler_ids)
            or tuple(sorted(set(self.compiler_ids))) != self.compiler_ids
        ):
            raise ValueError("invalid_comparison_context")
        return self


class ComparisonCaseSide(FrozenModel):
    input_hash: ContentHash
    image_treatment_hash: ContentHash | None = Field(default=None, exclude_if=lambda v: v is None)
    request_hash: ContentHash | None = None
    status: Status
    answer_option_id: ResourceId | None
    expected_option_ids: tuple[ResourceId, ...]
    label_provenance: str | None
    exclusion_reasons: tuple[str, ...]
    correct: bool | None

    @model_validator(mode="after")
    def coherent_assessment(self) -> Self:
        if (
            len(set(self.expected_option_ids)) != len(self.expected_option_ids)
            or (
                self.status != "valid"
                and (self.answer_option_id is not None or self.correct is not None)
            )
            or (
                self.correct is not None
                and (not self.expected_option_ids or self.answer_option_id is None)
            )
        ):
            raise ValueError("invalid_comparison_assessment")
        return self


class ComparedCase(FrozenModel):
    case_id: ResourceId
    bucket: Bucket
    left: ComparisonCaseSide | None
    right: ComparisonCaseSide | None


class ComparisonOutcomes(Record):
    profile: Literal["deykit-comparison-v1"] = "deykit-comparison-v1"
    left: ComparisonContext
    right: ComparisonContext
    cases: tuple[ComparedCase, ...]
    primary_counts: dict[Bucket, int]
    left_status_counts: dict[Status, int]
    right_status_counts: dict[Status, int]
    left_exclusion_counts: dict[str, int]
    right_exclusion_counts: dict[str, int]
    quality_denominator: int = Field(ge=0)
    left_correct_count: int = Field(ge=0)
    right_correct_count: int = Field(ge=0)
    unlabelled_denominator: int = Field(ge=0)

    @model_validator(mode="after")
    def conserved_counts(self) -> Self:
        ids = tuple(case.case_id for case in self.cases)
        if ids != tuple(
            sorted(set(self.left.selected_case_ids) | set(self.right.selected_case_ids))
        ):
            raise ValueError("comparison_union_mismatch")
        compatible = self.left.question_id == self.right.question_id and set(
            self.left.option_ids
        ) == set(self.right.option_ids)
        if any(
            case.bucket != classify(case.left, case.right, compatible_options=compatible)
            for case in self.cases
        ):
            raise ValueError("comparison_bucket_mismatch")
        counts = {bucket: sum(case.bucket == bucket for case in self.cases) for bucket in BUCKETS}
        if self.primary_counts != counts:
            raise ValueError("comparison_counts_mismatch")
        paired = (
            counts["both_correct"] + counts["improved"] + counts["regressed"] + counts["both_wrong"]
        )
        if (
            self.quality_denominator != paired
            or self.left_correct_count != counts["both_correct"] + counts["regressed"]
            or self.right_correct_count != counts["both_correct"] + counts["improved"]
            or self.unlabelled_denominator
            != counts["unlabelled_agreement"] + counts["unlabelled_disagreement"]
        ):
            raise ValueError("comparison_denominator_mismatch")
        for name in ("left", "right"):
            sides = tuple(
                getattr(case, name) for case in self.cases if getattr(case, name) is not None
            )
            statuses = {status: sum(side.status == status for side in sides) for status in STATUSES}
            reasons: dict[str, int] = {}
            for side in sides:
                for reason in set(side.exclusion_reasons):
                    reasons[reason] = reasons.get(reason, 0) + 1
            if (
                getattr(self, f"{name}_status_counts") != statuses
                or getattr(self, f"{name}_exclusion_counts") != reasons
            ):
                raise ValueError("comparison_side_counts_mismatch")
            context = getattr(self, name)
            actual = {case.case_id for case in self.cases if getattr(case, name) is not None}
            if actual != set(context.selected_case_ids):
                raise ValueError("comparison_side_scope_mismatch")
        if (
            self.left.decision_id != self.right.decision_id
            or self.left.dataset_id != self.right.dataset_id
        ):
            raise ValueError("comparison_resource_mismatch")
        return self
