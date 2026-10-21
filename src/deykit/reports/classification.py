"""Pure classification preset over admitted, frozen report evaluations."""

from decimal import Decimal, localcontext

from deykit.metrics.summary import Rate
from deykit.reports.models import (
    ClassificationCase,
    ClassificationEvaluation,
    ClassificationPricing,
    ClassificationReport,
    ClassMetricDisplay,
    RateDisplay,
    ReportEvaluation,
    StatusCounts,
    TokenListCost,
)


def rate(numerator: int, denominator: int, reason: str) -> RateDisplay:
    return RateDisplay.model_validate(Rate.counts(numerator, denominator, reason).source())


def _cost(evaluation: ReportEvaluation, pricing: ClassificationPricing) -> TokenListCost:
    context, usage = evaluation.context, evaluation.metrics.usage
    price = next(
        (
            item
            for item in pricing.rates
            if (item.adapter, item.requested_model) == (context.adapter, context.requested_model)
        ),
        None,
    )
    unknown = usage.dispatched_attempt_count - usage.reported_attempt_count
    reason: str | None = None
    subtotal = total = None
    if context.evidence_mode == "fixture":
        reason = "fixture_no_usage"
    elif price is None:
        reason = "pricing_source_unavailable"
    elif usage.reported_input_tokens is None or usage.reported_output_tokens is None:
        reason = "usage_not_reported"
    else:
        # Token counts are unbounded exact integers; never round them in the
        # process-wide Decimal context, or use binary floating point for money.
        with localcontext() as decimal_context:
            decimal_context.prec = (
                max(len(str(usage.reported_input_tokens)), len(str(usage.reported_output_tokens)))
                + 40
            )
            amount = (
                Decimal(usage.reported_input_tokens) * Decimal(price.input_per_million)
                + Decimal(usage.reported_output_tokens) * Decimal(price.output_per_million)
            ) / Decimal(1_000_000)
            subtotal = format(amount, "f")
        if usage.total_input_tokens is not None and usage.total_output_tokens is not None:
            total = subtotal
        else:
            reason = "partial_reported_usage"
    return TokenListCost(
        price=price,
        reported_subtotal=subtotal,
        total=total,
        unknown_attempt_count=unknown,
        reason=reason,
    )


def classify_evaluation(
    evaluation: ReportEvaluation, pricing: ClassificationPricing
) -> ClassificationEvaluation:
    # These exclusions concern answers or single-label metrics, not whether a
    # frozen expectation applies. All label exclusions continue to exclude it.
    answer_reasons = {
        "no_valid_answer",
        "incompatible_answer",
        "acceptable_set_excluded_from_class_metrics",
    }
    cases = tuple(
        ClassificationCase(
            case_id=case.case_id,
            applicable=bool(case.expected_option_ids)
            and not (set(case.exclusion_reasons) - answer_reasons),
            strict_correct=(case.status == "valid" and case.correct is True)
            if case.expected_option_ids and not (set(case.exclusion_reasons) - answer_reasons)
            else None,
        )
        for case in evaluation.cases
    )
    applicable_ids = {case.case_id for case in cases if case.applicable}
    applicable = tuple(case for case in evaluation.cases if case.case_id in applicable_ids)
    statuses = StatusCounts(
        **{
            status: sum(case.status == status for case in applicable)
            for status in ("pending", "input_invalid", "response_error", "unknown", "valid")
        }
    )
    singles = tuple(case for case in applicable if len(case.expected_option_ids) == 1)
    classes = []
    for option in evaluation.context.option_ids:
        support = sum(case.expected_option_ids == (option,) for case in singles)
        predicted = sum(
            case.status == "valid" and case.correct is not None and case.answer_option_id == option
            for case in singles
        )
        tp = sum(
            case.status == "valid"
            and case.correct is True
            and case.answer_option_id == option
            and case.expected_option_ids == (option,)
            for case in singles
        )
        classes.append(
            ClassMetricDisplay(
                option_id=option,
                support=support,
                predicted=predicted,
                true_positive=tp,
                precision=rate(tp, predicted, "no_predictions"),
                recall=rate(tp, support, "no_expected_cases"),
                f1=rate(2 * tp, support + predicted, "no_class_evidence"),
            )
        )
    correct = sum(case.strict_correct is True for case in cases)
    valid_count = sum(case.correct is not None for case in applicable)
    return ClassificationEvaluation(
        evaluation_id=evaluation.context.evaluation_id,
        selected_count=len(cases),
        applicable_count=len(applicable),
        excluded_count=len(cases) - len(applicable),
        full_cohort_strict_accuracy=rate(correct, len(applicable), "no_applicable_expectations"),
        valid_answer_accuracy=rate(correct, valid_count, "no_valid_applicable_answers"),
        applicable_status_counts=statuses,
        failed_count=statuses.input_invalid + statuses.response_error,
        missing_count=statuses.pending,
        class_count=len(singles),
        classes=tuple(classes),
        cases=cases,
        cost=_cost(evaluation, pricing),
    )


def classification_report(
    evaluations: tuple[ReportEvaluation, ...], pricing: ClassificationPricing
) -> ClassificationReport:
    limitations = ClassificationReport.model_fields["treatment_limitations"].default
    if any(case.selected_images for evaluation in evaluations for case in evaluation.cases):
        limitations = (
            "cohort_selection_does_not_establish_representativeness",
            "managed_images_record_source_and_prepared_identities",
            "compatible_pairs_do_not_establish_model_only_causality",
        )
    return ClassificationReport(
        pricing=pricing,
        evaluations=tuple(classify_evaluation(item, pricing) for item in evaluations),
        treatment_limitations=limitations,
    )
