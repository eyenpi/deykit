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
            if report.policy != "classification-strict-v1"
            else "- Refusals: unavailable (distinct_refusal_status_not_recorded); response errors "
            "may include refusals. No refusal is inferred from raw response text."
        ),
    ]
    experimental = report.experimental_comparison
    if experimental is not None:
        model_changed = (
            "unavailable (redacted)"
            if experimental.requested_model_changed is None
            else str(experimental.requested_model_changed).lower()
        )
        lines += [
            "",
            "### Experimental paired comparison",
            "",
            f"- Policy: {experimental.policy}. Cases need the same ID, question and option IDs, "
            "matching applicable expectations, and valid answers on both sides. "
            "Changed inputs and image treatments are allowed.",
            "- This denominator excludes missing or invalid answers. It differs from the "
            "full-cohort strict accuracy denominator above. Changes do not establish a "
            "model-only causal effect.",
            f"- Paired quality denominator: {experimental.quality_denominator}; "
            f"left correct: {experimental.left_correct_count}; "
            f"right correct: {experimental.right_correct_count}",
            "",
            "| Experimental pair outcome | Cases |",
            "| --- | ---: |",
        ]
        lines.extend(f"| {bucket} | {count} |" for bucket, count in experimental.counts.items())
        lines += [
            "",
            f"Treatment counts cover all {experimental.paired_case_count} case IDs present "
            "on both sides, including excluded pairs. Counts can overlap. Image source, "
            "prepared bytes and preparation settings compare only image names selected "
            "on both sides; added, removed or reordered names are counted separately.",
            "",
            "| Recorded difference | Cases |",
            "| --- | ---: |",
            f"| Case input identity | {experimental.input_identity_changed_count} |",
            f"| Prepared request bytes | {experimental.request_bytes_changed_count} |",
            f"| Prepared request unavailable | {experimental.request_bytes_unavailable_count} |",
            f"| Image presence | {experimental.image_presence_changed_count} |",
            "| Selected image names or order | "
            f"{experimental.selected_image_names_changed_count} |",
            f"| Shared image source | {experimental.image_source_changed_count} |",
            f"| Shared prepared image | {experimental.prepared_image_changed_count} |",
            f"| Shared image preparation settings | {experimental.preparation_changed_count} |",
            "",
            "Case input identity includes the original case input and source images, including "
            "images a decision did not select. Prepared request bytes also reflect provider "
            "formatting, model and instructions; their differences cannot identify the cause.",
            "- Selected model input comparison: unavailable (not recorded).",
            f"- Definition changed: {str(experimental.definition_changed).lower()}; "
            f"adapter changed: {str(experimental.adapter_changed).lower()}; "
            f"requested model changed: {model_changed}; "
            f"provider configuration changed: {str(experimental.provider_config_changed).lower()}",
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
    if report.policy != "classification-strict-v1":
        columns += ("explicit_refusal", "refused_count", "refusal_reason")
    if report.experimental_comparison is not None:
        columns += (
            "experimental_pair_bucket",
            "experimental_pair_row",
            "experimental_quality_denominator",
            "selected_input_comparison",
            "definition_changed",
            "adapter_changed",
            "requested_model_changed",
            "provider_config_changed",
            "input_identity_changed",
            "request_bytes_changed",
            "image_presence_changed",
            "selected_image_names_changed",
            "image_source_changed",
            "prepared_image_changed",
            "preparation_changed",
        )
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    buckets = (
        {case.case_id: case.bucket for case in content.comparison.cases}
        if (content.comparison is not None)
        else {}
    )
    experimental = report.experimental_comparison
    experimental_cases = {case.case_id: case for case in experimental.cases} if experimental else {}
    left_case_ids = (
        {case.case_id for case in content.evaluations[0].cases} if experimental else set()
    )
    for index, (evaluation, summary) in enumerate(
        zip(content.evaluations, report.evaluations, strict=True)
    ):
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
            if report.policy != "classification-strict-v1":
                row.update(
                    explicit_refusal=str(explicit_refusal(case)).lower(),
                    refused_count=str(summary.refused_count),
                    refusal_reason=summary.refusal_reason,
                )
            if experimental is not None:
                pair = experimental_cases[case.case_id]
                row.update(
                    experimental_pair_bucket=pair.bucket,
                    experimental_pair_row=str(
                        index == 0 or case.case_id not in left_case_ids
                    ).lower(),
                    experimental_quality_denominator=str(experimental.quality_denominator),
                    selected_input_comparison=experimental.selected_input_comparison,
                    definition_changed=str(experimental.definition_changed).lower(),
                    adapter_changed=str(experimental.adapter_changed).lower(),
                    requested_model_changed=(
                        "unavailable"
                        if experimental.requested_model_changed is None
                        else str(experimental.requested_model_changed).lower()
                    ),
                    provider_config_changed=str(experimental.provider_config_changed).lower(),
                )
                for field in (
                    "input_identity_changed",
                    "request_bytes_changed",
                    "image_presence_changed",
                    "selected_image_names_changed",
                    "image_source_changed",
                    "prepared_image_changed",
                    "preparation_changed",
                ):
                    value = getattr(pair, field)
                    row[field] = "" if value is None else str(value).lower()
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
