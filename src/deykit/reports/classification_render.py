"""Classification tables and spreadsheet-safe case exports from one saved report."""

import csv
import io
from collections.abc import Callable

from deykit.contracts.json_value import dump_json
from deykit.contracts.records import ReportRecord
from deykit.reports.classification import explicit_refusal
from deykit.reports.models import RateDisplay, ReportContent


def _rate(value: RateDisplay) -> str:
    return (
        f"{value.value} ({value.numerator}/{value.denominator})"
        if value.value
        else (f"unavailable ({value.reason})")
    )


def classification_markdown(content: ReportContent, inline: Callable[[object], str]) -> list[str]:
    report = content.classification
    if report is None:
        return []
    lines = [
        "",
        "## Classification experiment",
        "",
        f"- Policy: {report.policy}; category-only scoring: {report.category_only_scoring}",
        "- Label applicability: frozen expectations with no label exclusion; unlabelled, "
        "disputed, stale and incompatible expectations are excluded, regardless of answer status.",
        "- Full-cohort strict accuracy: correct valid answers / all applicable expectations; "
        "failed, missing and unknown answers remain in the denominator.",
        f"- Comparison policy: {report.comparison_policy}; existing paired improvements, "
        "regressions and all exclusion buckets appear below.",
        "- Strict class metrics: applicable single labels including failures as false negatives; "
        "acceptable sets are scored for accuracy only.",
        f"- Latency population: {report.latency_population}; p50/p95 use nearest rank, "
        "not case totals or wall-clock experiment time. Fixture latency is unavailable.",
        "- Treatment limitations: " + "; ".join(report.treatment_limitations),
        (
            "- Refusals: explicit provider_refusal response errors among applicable expectations; "
            "a subset of failed answers, already included in strict accuracy. Zero means no "
            "explicit markers. Other response errors may include unmarked refusals."
            if report.policy == "classification-strict-v2"
            else "- Refusals: unavailable (distinct_refusal_status_not_recorded); response errors "
            "may include refusals. No refusal is inferred from raw response text."
        ),
    ]
    for summary in report.evaluations:
        counts = summary.applicable_status_counts
        refusals = (
            f"explicit refusals {summary.refused_count}."
            if summary.refused_count is not None
            else "refused unavailable."
        )
        lines += [
            "",
            f"### Classification evaluation `{summary.evaluation_id}`",
            "",
            f"- Selected: {summary.selected_count}; applicable: {summary.applicable_count}; "
            f"excluded expectations: {summary.excluded_count}",
            "- Full-cohort strict accuracy: " + _rate(summary.full_cohort_strict_accuracy),
            "- Valid-answer accuracy: " + _rate(summary.valid_answer_accuracy),
            f"- Applicable outcomes: valid {counts.valid}; failed {summary.failed_count} "
            f"(input invalid {counts.input_invalid}, response error {counts.response_error}); "
            f"missing {summary.missing_count}; unknown {counts.unknown}; {refusals}",
            f"- Strict class population: {summary.class_count}",
            "",
            "| Option | Support | Predicted | True positive | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
        for item in summary.classes:
            lines.append(
                f"| {inline(item.option_id)} | {item.support} | {item.predicted} | "
                f"{item.true_positive} | "
                f"{_rate(item.precision)} | {_rate(item.recall)} | {_rate(item.f1)} |"
            )
        cost = summary.cost
        lines += [
            "",
            "#### Token-list cost estimate",
            "",
            f"- Reported subtotal: {cost.reported_subtotal or 'unavailable'}; "
            f"total: {cost.total or 'unavailable'}; "
            f"attempts without usage: {cost.unknown_attempt_count}; "
            f"reason: {cost.reason or 'complete'}; {cost.interpretation}",
        ]
        if cost.price:
            price = cost.price
            lines.append(
                f"- Frozen rates: {price.currency} {price.input_per_million} input / "
                f"{price.output_per_million} output per million tokens; "
                f"source: {inline(price.source)}; as of: {price.as_of}"
            )
    return lines


def classification_csv(record: ReportRecord, content: ReportContent) -> bytes:
    report = content.classification
    if report is None:
        raise ValueError("csv_requires_classification")
    output = io.StringIO(newline="")
    columns: tuple[str, ...] = (
        "report_id",
        "content_hash",
        "evaluation_id",
        "run_id",
        "result_snapshot_id",
        "label_snapshot_id",
        "evidence_mode",
        "requested_model",
        "case_id",
        "input_hash",
        "selected_images",
        "split",
        "status",
        "attempt_id",
        "answer_option_id",
        "expected_option_ids",
        "label_provenance",
        "exclusion_reasons",
        "error_reason",
        "label_applicable",
        "strict_correct",
        "selected_count",
        "applicable_count",
        "strict_correct_count",
        "comparison_bucket",
        "token_list_total",
        "token_list_currency",
        "cost_reason",
    )
    if report.policy == "classification-strict-v2":
        columns += ("explicit_refusal", "refused_count", "refusal_reason")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    buckets = (
        {case.case_id: case.bucket for case in content.comparison.cases}
        if (content.comparison is not None)
        else {}
    )
    for evaluation, summary in zip(content.evaluations, report.evaluations, strict=True):
        context = evaluation.context
        for case, assessment in zip(evaluation.cases, summary.cases, strict=True):
            row = {
                "report_id": record.id,
                "content_hash": record.content_hash,
                "evaluation_id": context.evaluation_id,
                "run_id": context.run_id,
                "result_snapshot_id": context.result_snapshot_id,
                "label_snapshot_id": context.label_snapshot_id,
                "evidence_mode": context.evidence_mode,
                "requested_model": context.requested_model,
                "case_id": case.case_id,
                "input_hash": case.input_hash,
                "selected_images": dump_json(
                    [image.model_dump(mode="json") for image in case.selected_images]
                ),
                "split": case.split,
                "status": case.status,
                "attempt_id": case.attempt_id or "",
                "answer_option_id": case.answer_option_id or "",
                "expected_option_ids": dump_json(list(case.expected_option_ids)),
                "label_provenance": case.label_provenance or "",
                "exclusion_reasons": dump_json(list(case.exclusion_reasons)),
                "error_reason": (case.error.reason or case.error.code) if case.error else "",
                "label_applicable": str(assessment.applicable).lower(),
                "strict_correct": str(assessment.strict_correct).lower()
                if assessment.strict_correct is not None
                else "",
                "selected_count": str(summary.selected_count),
                "applicable_count": str(summary.applicable_count),
                "strict_correct_count": str(summary.full_cohort_strict_accuracy.numerator),
                "comparison_bucket": buckets.get(case.case_id, ""),
                "token_list_total": summary.cost.total or "",
                "token_list_currency": summary.cost.price.currency if summary.cost.price else "",
                "cost_reason": summary.cost.reason or "",
            }
            if report.policy == "classification-strict-v2":
                row.update(
                    explicit_refusal=str(explicit_refusal(case)).lower(),
                    refused_count=str(summary.refused_count),
                    refusal_reason=summary.refusal_reason,
                )
            writer.writerow(
                {
                    key: "'" + value
                    if value.lstrip().startswith(("=", "+", "-", "@"))
                    or value.startswith(("\t", "\r", "\n"))
                    else value
                    for key, value in row.items()
                }
            )
    return output.getvalue().encode("utf-8", "strict")
