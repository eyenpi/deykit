"""Disjoint case accounting over pre-assessed immutable values."""

from deykit.comparisons.models import (
    BUCKETS,
    STATUSES,
    Bucket,
    ComparedCase,
    ComparisonCaseSide,
    ComparisonContext,
    ComparisonOutcomes,
)
from deykit.contracts.model_admission import admit_model


def classify(
    left: ComparisonCaseSide | None, right: ComparisonCaseSide | None, *, compatible_options: bool
) -> Bucket:
    if left is None:
        return "right_only"
    if right is None:
        return "left_only"
    if left.input_hash != right.input_hash:
        return "changed_input"
    if not compatible_options:
        return "changed_question_options"
    if set(left.expected_option_ids) != set(right.expected_option_ids):
        return "changed_expectations"
    if left.status != "valid" or right.status != "valid":
        return "unavailable_answer"
    if left.correct is not None and right.correct is not None:
        if left.correct and right.correct:
            return "both_correct"
        if right.correct:
            return "improved"
        return "regressed" if left.correct else "both_wrong"
    if (
        not left.expected_option_ids
        and not right.expected_option_ids
        and set(left.exclusion_reasons) == {"unlabelled"}
        and set(right.exclusion_reasons) == {"unlabelled"}
    ):
        return (
            "unlabelled_agreement"
            if left.answer_option_id == right.answer_option_id
            else "unlabelled_disagreement"
        )
    return "excluded_expectation"


def pair_cases(
    left_context: ComparisonContext,
    right_context: ComparisonContext,
    left_cases: dict[str, ComparisonCaseSide],
    right_cases: dict[str, ComparisonCaseSide],
) -> ComparisonOutcomes:
    left_context = admit_model(ComparisonContext, left_context, "invalid_comparison_context")
    right_context = admit_model(ComparisonContext, right_context, "invalid_comparison_context")
    if (
        left_context.decision_id != right_context.decision_id
        or left_context.dataset_id != right_context.dataset_id
    ):
        raise ValueError("comparison_resource_mismatch")
    left_cases = {
        key: admit_model(ComparisonCaseSide, value, "invalid_comparison_case")
        for key, value in left_cases.items()
    }
    right_cases = {
        key: admit_model(ComparisonCaseSide, value, "invalid_comparison_case")
        for key, value in right_cases.items()
    }
    compatible = left_context.question_id == right_context.question_id and set(
        left_context.option_ids
    ) == set(right_context.option_ids)
    cases = tuple(
        ComparedCase(
            case_id=case_id,
            bucket=classify(
                left_cases.get(case_id), right_cases.get(case_id), compatible_options=compatible
            ),
            left=left_cases.get(case_id),
            right=right_cases.get(case_id),
        )
        for case_id in sorted(set(left_cases) | set(right_cases))
    )
    counts = {bucket: sum(case.bucket == bucket for case in cases) for bucket in BUCKETS}

    def reasons(sides: dict[str, ComparisonCaseSide]) -> dict[str, int]:
        result: dict[str, int] = {}
        for side in sides.values():
            for reason in set(side.exclusion_reasons):
                result[reason] = result.get(reason, 0) + 1
        return result

    return ComparisonOutcomes(
        left=left_context,
        right=right_context,
        cases=cases,
        primary_counts=counts,
        left_status_counts={
            status: sum(side.status == status for side in left_cases.values())
            for status in STATUSES
        },
        right_status_counts={
            status: sum(side.status == status for side in right_cases.values())
            for status in STATUSES
        },
        left_exclusion_counts=reasons(left_cases),
        right_exclusion_counts=reasons(right_cases),
        quality_denominator=counts["both_correct"]
        + counts["improved"]
        + counts["regressed"]
        + counts["both_wrong"],
        left_correct_count=counts["both_correct"] + counts["regressed"],
        right_correct_count=counts["both_correct"] + counts["improved"],
        unlabelled_denominator=counts["unlabelled_agreement"] + counts["unlabelled_disagreement"],
    )
