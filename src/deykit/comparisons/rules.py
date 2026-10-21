"""One pure bucket classifier shared by creation and strict evidence decoding."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deykit.comparisons.models import Bucket, ComparisonCaseSide


def classify(
    left: ComparisonCaseSide | None, right: ComparisonCaseSide | None, *, compatible_options: bool
) -> Bucket:
    if left is None:
        return "right_only"
    if right is None:
        return "left_only"
    if (
        left.input_hash != right.input_hash
        or left.image_treatment_hash != right.image_treatment_hash
    ):
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
