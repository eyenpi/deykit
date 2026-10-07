"""Deterministic, side-effect-free report renderers."""

from __future__ import annotations

import hashlib
import re

from deykit.comparisons.models import BUCKETS
from deykit.contracts.json_value import JsonValue, dump_json, parse_json
from deykit.contracts.records import ReportRecord
from deykit.reports.models import RenderedArtifact, ReportContent, ReportFormat

_MAX_MARKDOWN_BYTES = 8 * 1024 * 1024


def _inline(value: object) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    return re.sub(r"([`*_{}\[\]<>!#])", r"\\\1", text)


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _rate(value: object) -> str:
    row = _mapping(value)
    display = row.get("value")
    numerator, denominator = row.get("numerator"), row.get("denominator")
    if display is None:
        return (
            f"Unavailable ({_inline(row.get('reason') or 'unavailable')}; "
            f"{numerator}/{denominator})"
        )
    return f"{_inline(display)} ({numerator}/{denominator})"


def _markdown(record: ReportRecord, content: ReportContent) -> str:
    target = content.target
    modes = (
        ", ".join(item.metrics.evidence_mode for item in content.evaluations)
        or "comparison evidence"
    )
    lines = [
        "# Evidence report",
        "",
        f"- Report: `{_inline(record.id)}`",
        f"- Target: `{_inline(target.kind)}` `{_inline(target.target_id)}`",
        f"- Created: `{_inline(record.created_at)}`",
        f"- Content hash: `{record.content_hash}`",
        f"- Evidence modes: {_inline(modes)}",
        f"- Limitations: {_inline(', '.join(content.limitations) or 'none')}",
        "",
        "## Frozen source context",
        "",
        f"- Evaluations: {_inline(', '.join(target.evaluation_ids) or 'none')}",
        f"- Results: {_inline(', '.join(target.result_snapshot_ids) or 'none')}",
        f"- Labels: {_inline(', '.join(target.label_snapshot_ids) or 'none')}",
    ]
    for number, evaluation in enumerate(content.evaluations, 1):
        metrics = evaluation.metrics
        summary = metrics.summary
        statuses = summary.status_counts.model_dump(mode="json")
        valid = summary.status_counts.valid
        selected = summary.selected_count
        partial = valid != selected
        lines += [
            "",
            f"## Evaluation {number}{' — partial' if partial else ''}",
            "",
            f"- Run: `{_inline(evaluation.context.run_id)}`",
            f"- Evaluation mode: {_inline(metrics.evaluation_mode)}",
            f"- Evidence mode: {_inline(metrics.evidence_mode)}",
            f"- Selected: {selected}; statuses: {_inline(statuses)}",
            f"- Coverage: {_rate(summary.coverage.model_dump(mode='json'))}",
            f"- Set accuracy: {_rate(summary.set_accuracy.model_dump(mode='json'))}",
            f"- Macro F1: {_rate(summary.macro_f1.model_dump(mode='json'))}",
        ]
        latency = metrics.latency
        usage = metrics.usage
        lines += [
            f"- Latency p50: {_inline(latency.p50_seconds)} s",
            f"- Latency p95: {_inline(latency.p95_seconds)} s",
            f"- Latency sample count: {latency.sample_count}",
            f"- Latency status: {_inline(latency.reason or latency.method)}",
            f"- Reported input tokens: {_inline(usage.reported_input_tokens)}",
            f"- Reported output tokens: {_inline(usage.reported_output_tokens)}",
            f"- Total input tokens: {_inline(usage.total_input_tokens)}",
            f"- Total output tokens: {_inline(usage.total_output_tokens)}",
            f"- Usage status: {_inline(usage.reason or usage.source_kind or 'unavailable')}",
            "- Cost: unavailable (pricing source unavailable)",
        ]
        baseline = metrics.baseline
        lines.extend(
            (
                f"- Majority baseline: {_inline(baseline.option_id or 'unavailable')} "
                f"accuracy {_rate(baseline.accuracy.model_dump(mode='json'))}",
                f"- Baseline fitting support: {baseline.fit_support}; "
                f"paired population: {baseline.scored_count}/{baseline.paired_count}",
                f"- Baseline fitting snapshots: `{baseline.fit_dataset_snapshot_id}` / "
                f"`{baseline.fit_label_snapshot_id}`",
                f"- Baseline overlap cases: {_inline(baseline.overlap_case_ids or 'none')}",
            )
        )
        lines += [
            "",
            "### Class metrics",
            "",
            "| Option | Support | Predicted | True positive | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for class_metric in summary.classes:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _inline(class_metric.option_id),
                        str(class_metric.support),
                        str(class_metric.predicted),
                        str(class_metric.true_positive),
                        _rate(class_metric.precision.model_dump(mode="json")),
                        _rate(class_metric.recall.model_dump(mode="json")),
                        _rate(class_metric.f1.model_dump(mode="json")),
                    )
                )
                + " |"
            )
        lines += [
            "",
            "### Confusion matrix",
            "",
            "Rows are expected options; columns are predicted options in saved option order.",
            "",
            "| Expected \\ Predicted | "
            + " | ".join(_inline(item) for item in summary.option_ids)
            + " |",
            "| --- | " + " | ".join("---:" for _ in summary.option_ids) + " |",
        ]
        for option_id, row in zip(summary.option_ids, summary.confusion_matrix, strict=True):
            lines.append(
                "| " + _inline(option_id) + " | " + " | ".join(str(value) for value in row) + " |"
            )
        lines += [
            "",
            "### Case outcomes",
            "",
            "| Case | Status | Answer | Expected | Correct | Exclusions or error |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for evaluation_case in evaluation.cases:
            error = evaluation_case.error.reason if evaluation_case.error else None
            detail = (
                "; ".join((*evaluation_case.exclusion_reasons, *((error,) if error else ())))
                or "none"
            )
            lines.append(
                "| "
                + " | ".join(
                    (
                        _inline(evaluation_case.case_id),
                        _inline(evaluation_case.status),
                        _inline(evaluation_case.answer_option_id or "unavailable"),
                        _inline(evaluation_case.expected_option_ids or "unlabelled"),
                        _inline(
                            evaluation_case.correct
                            if evaluation_case.correct is not None
                            else "not scored"
                        ),
                        _inline(detail),
                    )
                )
                + " |"
            )
        context = evaluation.context
        lines.extend(
            (
                f"- Requested model: {_inline(context.requested_model)}",
                f"- Answering models: {_inline(context.answering_models)}",
                f"- Compilers: {_inline(context.compiler_ids)} "
                f"({_inline(context.compiler_version)})",
                f"- Option order: {_inline(context.option_order)}",
            )
        )
    if content.comparison is not None:
        comparison = content.comparison
        lines += [
            "",
            "## Comparison",
            "",
            f"- Left model: {_inline(comparison.left.requested_model)}",
            f"- Right model: {_inline(comparison.right.requested_model)}",
            f"- Left option order: {_inline(comparison.left.option_order)}",
            f"- Right option order: {_inline(comparison.right.option_order)}",
            f"- Paired quality denominator: {comparison.quality_denominator}",
            "",
            "| Outcome bucket | Cases |",
            "| --- | ---: |",
        ]
        for bucket in BUCKETS:
            lines.append(f"| {_inline(bucket)} | {comparison.primary_counts[bucket]} |")
        lines += [
            "",
            "### Case outcomes",
            "",
            "| Case | Bucket | Left status / answer | Right status / answer |",
            "| --- | --- | --- | --- |",
        ]
        for compared_case in comparison.cases:
            left = (
                f"{compared_case.left.status} / "
                f"{compared_case.left.answer_option_id or 'unavailable'}"
                if compared_case.left is not None
                else "not selected"
            )
            right = (
                f"{compared_case.right.status} / "
                f"{compared_case.right.answer_option_id or 'unavailable'}"
                if compared_case.right is not None
                else "not selected"
            )
            lines.append(
                "| "
                + " | ".join(
                    (
                        _inline(compared_case.case_id),
                        _inline(compared_case.bucket),
                        _inline(left),
                        _inline(right),
                    )
                )
                + " |"
            )
    if content.raw_material:
        lines += ["", "## Explicitly included raw material", ""]
        for item in content.raw_material:
            lines.append(
                f"### {_inline(item.category)}: run `{item.run_id}`, "
                f"case `{item.case_id}`, attempt `{item.attempt_id or 'none'}`"
            )
            lines.append(
                f"Encoding: `{item.encoding or 'unavailable'}`; "
                f"original hash: `{item.original_hash or 'unavailable'}`; "
                f"sanitized hash: `{item.sanitized_hash or 'unavailable'}`"
            )
            if item.source is None:
                lines.append(f"Unavailable: {_inline(item.unavailable_reason)}")
            else:
                source = item.source
                longest = max(
                    (len(match.group(0)) for match in re.finditer(r"`+", source)), default=0
                )
                fence = "`" * max(3, longest + 1)
                lines.extend((fence, source, fence))
    return "\n".join(lines).rstrip("\n") + "\n"


def render_content(
    record: ReportRecord, content: ReportContent, format: ReportFormat
) -> RenderedArtifact:
    if format not in ("json", "markdown"):
        raise ValueError("invalid_report_format")
    if format == "json":
        parsed = parse_json(record.content_source)
        envelope: JsonValue = {
            "schema_version": 1,
            "report_id": record.id,
            "created_at": record.created_at,
            "content_hash": record.content_hash,
            "content": parsed,
        }
        body = (dump_json(envelope, sort_keys=True) + "\n").encode("utf-8", "strict")
    else:
        body = _markdown(record, content).encode("utf-8", "strict")
        if len(body) > _MAX_MARKDOWN_BYTES:
            raise ValueError("report_artifact_limit")
    return RenderedArtifact(record.id, format, body, hashlib.sha256(body).hexdigest(), len(body))
