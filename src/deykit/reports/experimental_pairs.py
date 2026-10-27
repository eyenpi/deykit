"""Paired classification outcomes across explicitly recorded treatments."""

from deykit.comparisons.models import ComparedCase, ComparisonOutcomes
from deykit.reports.models import (
    ExperimentalComparison,
    ExperimentalPairBucket,
    ExperimentalPairCase,
    ReportCase,
    ReportEvaluation,
    SelectedInputDifference,
)

BUCKETS: tuple[ExperimentalPairBucket, ...] = (
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
)


def _bucket(
    case: ComparedCase, *, compatible_options: bool, incompatible_answer: bool
) -> ExperimentalPairBucket:
    left, right = case.left, case.right
    if left is None:
        return "right_only"
    if right is None:
        return "left_only"
    if not compatible_options:
        return "changed_question_options"
    if set(left.expected_option_ids) != set(right.expected_option_ids):
        return "changed_expectations"
    if left.status != "valid" or right.status != "valid" or incompatible_answer:
        return "unavailable_answer"
    if left.correct is None or right.correct is None:
        return "excluded_expectation"
    if left.correct and right.correct:
        return "both_correct"
    if right.correct:
        return "improved"
    return "regressed" if left.correct else "both_wrong"


def _case(
    case: ComparedCase,
    left: ReportCase | None,
    right: ReportCase | None,
    *,
    compatible_options: bool,
    left_question: str,
    right_question: str,
    left_options: set[str],
    right_options: set[str],
    selected_inputs: tuple[dict[str, str | None], dict[str, str | None]] | None,
) -> ExperimentalPairCase:
    if left is None or right is None:
        return ExperimentalPairCase(
            case_id=case.case_id,
            bucket=_bucket(case, compatible_options=compatible_options, incompatible_answer=False),
            input_identity_changed=None,
            request_bytes_changed=None,
            image_presence_changed=None,
            selected_image_names_changed=None,
            image_source_changed=None,
            prepared_image_changed=None,
            preparation_changed=None,
            selected_input=(
                SelectedInputDifference(changed=None, unavailable_reason="case_missing")
                if selected_inputs is not None
                else None
            ),
        )
    assert case.left is not None and case.right is not None
    left_images = {image.name: image.asset for image in left.selected_images}
    right_images = {image.name: image.asset for image in right.selected_images}
    shared_images = left_images.keys() & right_images.keys()
    left_request, right_request = case.left.request_hash, case.right.request_hash
    selected_input = None
    if selected_inputs is not None:
        if case.case_id not in selected_inputs[0] or case.case_id not in selected_inputs[1]:
            raise ValueError("selected_input_identity_missing")
        left_hash = selected_inputs[0][case.case_id]
        right_hash = selected_inputs[1][case.case_id]
        selected_input = SelectedInputDifference(
            changed=left_hash != right_hash
            if left_hash is not None and right_hash is not None
            else None,
            unavailable_reason=(
                "input_not_prepared" if left_hash is None or right_hash is None else None
            ),
        )
    incompatible_answer = (
        left.status == "valid"
        and (left.answer_question_id != left_question or left.answer_option_id not in left_options)
    ) or (
        right.status == "valid"
        and (
            right.answer_question_id != right_question
            or right.answer_option_id not in right_options
        )
    )
    return ExperimentalPairCase(
        case_id=case.case_id,
        bucket=_bucket(
            case, compatible_options=compatible_options, incompatible_answer=incompatible_answer
        ),
        input_identity_changed=case.left.input_hash != case.right.input_hash,
        request_bytes_changed=(
            left_request != right_request
            if left_request is not None and right_request is not None
            else None
        ),
        image_presence_changed=bool(left_images) != bool(right_images),
        selected_image_names_changed=tuple(image.name for image in left.selected_images)
        != tuple(image.name for image in right.selected_images),
        image_source_changed=any(
            left_images[name].source.content_hash != right_images[name].source.content_hash
            for name in shared_images
        ),
        prepared_image_changed=any(
            left_images[name].prepared.content_hash != right_images[name].prepared.content_hash
            for name in shared_images
        ),
        preparation_changed=any(
            left_images[name].preparation != right_images[name].preparation
            for name in shared_images
        ),
        selected_input=selected_input,
    )


def experimental_comparison(
    comparison: ComparisonOutcomes,
    evaluations: tuple[ReportEvaluation, ...],
    *,
    selected_inputs: tuple[dict[str, str | None], dict[str, str | None]] | None = None,
) -> ExperimentalComparison:
    left, right = evaluations
    left_cases = {case.case_id: case for case in left.cases}
    right_cases = {case.case_id: case for case in right.cases}
    left_options, right_options = set(comparison.left.option_ids), set(comparison.right.option_ids)
    compatible = (
        comparison.left.question_id == comparison.right.question_id
        and left_options == right_options
    )
    cases = tuple(
        _case(
            case,
            left_cases.get(case.case_id),
            right_cases.get(case.case_id),
            compatible_options=compatible,
            left_question=comparison.left.question_id,
            right_question=comparison.right.question_id,
            left_options=left_options,
            right_options=right_options,
            selected_inputs=selected_inputs,
        )
        for case in comparison.cases
    )
    counts = {bucket: sum(case.bucket == bucket for case in cases) for bucket in BUCKETS}
    paired = tuple(case for case in cases if case.input_identity_changed is not None)
    return ExperimentalComparison(
        policy="matching_labels_allow_changed_inputs_v1",
        selected_input_comparison=(
            "reconstructed_selection_v1" if selected_inputs is not None else "not_recorded"
        ),
        counts=counts,
        quality_denominator=(
            counts["both_correct"] + counts["improved"] + counts["regressed"] + counts["both_wrong"]
        ),
        left_correct_count=counts["both_correct"] + counts["regressed"],
        right_correct_count=counts["both_correct"] + counts["improved"],
        paired_case_count=len(paired),
        input_identity_changed_count=sum(case.input_identity_changed is True for case in paired),
        request_bytes_changed_count=sum(case.request_bytes_changed is True for case in paired),
        request_bytes_unavailable_count=sum(case.request_bytes_changed is None for case in paired),
        image_presence_changed_count=sum(case.image_presence_changed is True for case in paired),
        selected_image_names_changed_count=sum(
            case.selected_image_names_changed is True for case in paired
        ),
        image_source_changed_count=sum(case.image_source_changed is True for case in paired),
        prepared_image_changed_count=sum(case.prepared_image_changed is True for case in paired),
        preparation_changed_count=sum(case.preparation_changed is True for case in paired),
        selected_input_changed_count=(
            sum(
                case.selected_input is not None and case.selected_input.changed is True
                for case in paired
            )
            if selected_inputs is not None
            else None
        ),
        selected_input_unavailable_count=(
            sum(
                case.selected_input is not None and case.selected_input.changed is None
                for case in paired
            )
            if selected_inputs is not None
            else None
        ),
        definition_changed=comparison.left.definition_hash != comparison.right.definition_hash,
        adapter_changed=comparison.left.adapter != comparison.right.adapter,
        requested_model_changed=(
            None
            if any(
                "[REDACTED]" in name
                for name in (comparison.left.requested_model, comparison.right.requested_model)
            )
            else comparison.left.requested_model != comparison.right.requested_model
        ),
        provider_config_changed=(
            comparison.left.provider_config_hash != comparison.right.provider_config_hash
        ),
        cases=cases,
    )
