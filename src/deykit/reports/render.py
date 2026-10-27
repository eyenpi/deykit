"""Deterministic, side-effect-free report renderers."""

from __future__ import annotations

import hashlib
import re

from deykit.comparisons.models import BUCKETS
from deykit.contracts.json_value import JsonValue, dump_json, parse_json
from deykit.contracts.records import ReportRecord
from deykit.contracts.report_json import (
    REPORT_ARTIFACT_MAX_BYTES,
    REPORT_CONTENT_LIMITS,
    REPORT_RECORD_LIMITS,
)
from deykit.reports.models import (
    MemberEvidenceContext,
    RenderedArtifact,
    ReportContent,
    ReportFormat,
)


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


def _group_member_context(number: int, member: MemberEvidenceContext) -> list[str]:
    """Render every stored member provenance link before the shared source index."""
    lines = [
        f"### Member {number}",
        "",
        f"- Requested model: {_inline(member.requested_model)}",
        f"- Answering models: {_inline(member.answering_models or 'unavailable')}",
        f"- Compiler IDs and version: {_inline(member.compiler_ids)} / "
        f"{_inline(member.compiler_version or 'unavailable')}",
        f"- Option order: {_inline(member.option_order)}",
        f"- Run: `{_inline(member.run_id)}`; manifest hash: `{member.manifest_hash}`",
        f"- Mode: {_inline(member.evidence_mode)}; fixture set: "
        f"{_inline(member.fixture_set_id or 'unavailable')}",
        f"- Provider profile: `{_inline(member.provider_profile_id)}`; configuration hash: "
        f"`{member.provider_config_hash}`; adapter: `{_inline(member.adapter)}`",
        f"- Decision: `{_inline(member.decision_id)}`; revision: "
        f"`{_inline(member.decision_revision_id)}`; definition hash: `{member.definition_hash}`",
        f"- Dataset: `{_inline(member.dataset_id)}`; snapshot: "
        f"`{_inline(member.dataset_snapshot_id)}`; hash: `{member.dataset_hash}`",
        f"- Label snapshot: `{_inline(member.label_snapshot_id)}`; hash: `{member.label_hash}`",
        f"- Result snapshot: `{_inline(member.result_snapshot_id)}`; hash: "
        f"`{member.result_hash}`; event sequence: {member.through_event_sequence}",
        f"- Question: `{_inline(member.question_id)}`; options: {_inline(member.option_ids)}",
        f"- Selected cases: {_inline(member.selected_case_ids)}",
        f"- Baseline dataset snapshot: `{_inline(member.baseline_dataset_snapshot_id)}`; "
        f"hash: `{member.baseline_dataset_hash}`",
        f"- Baseline label snapshot: `{_inline(member.baseline_label_snapshot_id)}`; "
        f"hash: `{member.baseline_label_hash}`",
        "",
    ]
    for treatment in member.image_treatments:
        for image in treatment.selected_images:
            asset = image.asset
            lines.append(
                f"- Image for {_inline(treatment.case_id)} / {_inline(image.name)}: "
                f"asset `{asset.id}`; source `{asset.source.content_hash}` "
                f"({asset.source.width}x{asset.source.height} {asset.source.format}); "
                f"prepared `{asset.prepared.content_hash}` "
                f"({asset.prepared.width}x{asset.prepared.height} {asset.prepared.format}); "
                f"policy {_inline(asset.preparation.model_dump(mode='json'))}"
            )
    return lines


def _markdown(record: ReportRecord, content: ReportContent) -> str:
    target = content.target
    modes = (
        ", ".join(item.metrics.evidence_mode for item in content.evaluations)
        or ", ".join(
            member.evidence_mode
            for group in (content.diagnostic, content.check)
            if group is not None
            for member in group.members
        )
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
    ]
    from deykit.reports.classification_render import classification_markdown

    lines.extend(classification_markdown(content, _inline))
    if content.evaluations:
        lines += ["", "## Evaluation contexts", ""]
        for number, evaluation in enumerate(content.evaluations, 1):
            context = evaluation.context
            lines += [
                f"### Evaluation {number}",
                "",
                f"- Evaluation: `{_inline(context.evaluation_id)}`",
                f"- Run: `{_inline(context.run_id)}`",
                f"- Requested model: {_inline(context.requested_model)}",
                f"- Answering models: {_inline(context.answering_models)}",
                f"- Compilers: {_inline(context.compiler_ids)} "
                f"({_inline(context.compiler_version)})",
                f"- Option order: {_inline(context.option_order)}",
                "",
            ]
    if content.diagnostic is None and content.check is None:
        lines += [
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
        baseline = metrics.baseline
        lines += [
            "",
            "### Baseline",
            "",
            f"- Majority: {_inline(baseline.option_id or 'unavailable')} "
            f"accuracy {_rate(baseline.accuracy.model_dump(mode='json'))}",
            f"- Fitting support: {baseline.fit_support}; excluded acceptable sets: "
            f"{baseline.fit_excluded_acceptable_sets}",
            f"- Fitting snapshots: `{baseline.fit_dataset_snapshot_id}` / "
            f"`{baseline.fit_label_snapshot_id}`",
            f"- Evaluation snapshots: `{baseline.evaluation_dataset_snapshot_id}` / "
            f"`{baseline.evaluation_label_snapshot_id}`",
            f"- Evaluation splits: {_inline(baseline.evaluation_splits or 'none')}",
            f"- Selected: {baseline.selected_count}; scoring population: "
            f"{_inline(baseline.scoring_population)}; scored: {baseline.scored_count}; "
            f"paired: {baseline.paired_count}",
            f"- Overlap cases: {_inline(baseline.overlap_case_ids or 'none')}",
            f"- Unavailable reason: {_inline(baseline.unavailable_reason or 'none')}",
            "",
            "### Latency and usage",
            "",
        ]
        latency = metrics.latency
        usage = metrics.usage
        classification = content.classification
        v4_summary = (
            classification.evaluations[number - 1]
            if classification is not None and classification.policy == "classification-strict-v4"
            else None
        )
        lines += [
            f"- Latency p50: {_inline(latency.p50_seconds)} s",
            f"- Latency p95: {_inline(latency.p95_seconds)} s",
            f"- Latency samples: {latency.sample_count}; status: "
            f"{_inline(latency.reason or latency.method)}",
            f"- Dispatched attempts: {usage.dispatched_attempt_count}; reported attempts: "
            f"{usage.reported_attempt_count}",
            f"- Reported input tokens: {_inline(usage.reported_input_tokens)}",
            f"- Reported output tokens: {_inline(usage.reported_output_tokens)}",
            f"- Total input tokens: {_inline(usage.total_input_tokens)}",
            f"- Total output tokens: {_inline(usage.total_output_tokens)}",
            f"- Usage source: {_inline(usage.source_kind or 'unavailable')}; reported at: "
            f"{_inline(usage.reported_at or 'unavailable')}",
            f"- Usage status: {_inline(usage.reason or usage.mode)}",
            (
                f"- Original evaluation cost: unavailable ({_inline(usage.cost_reason)}). "
                "See the token-list estimate in the classification section."
                if v4_summary is not None
                else f"- Cost: unavailable ({_inline(usage.cost_reason)})"
            ),
        ]
        case_columns = ["Case", "Status", "Answer", "Expected"]
        if v4_summary is not None:
            case_columns += ["Label provenance", "Legacy labels"]
        case_columns += ["Evaluation correct", "Strict correct"] if v4_summary else ["Correct"]
        if v4_summary is not None and v4_summary.category_only is not None:
            case_columns += ["Category source", "Category answer", "Category correct"]
        case_columns.append("Exclusions or error")
        classifications = (
            {case.case_id: case for case in v4_summary.cases} if v4_summary is not None else {}
        )
        lines += [
            "",
            "### Case outcomes",
            "",
            "| " + " | ".join(case_columns) + " |",
            "| " + " | ".join("---" for _ in case_columns) + " |",
        ]
        for evaluation_case in evaluation.cases:
            error = evaluation_case.error.reason if evaluation_case.error else None
            detail = (
                "; ".join((*evaluation_case.exclusion_reasons, *((error,) if error else ())))
                or "none"
            )
            expected: object = evaluation_case.expected_option_ids or "unlabelled"
            if v4_summary is not None and not evaluation_case.expected_option_ids:
                if evaluation_case.legacy_question_ids:
                    expected = "incompatible question"
            values: list[object] = [
                evaluation_case.case_id,
                evaluation_case.status,
                evaluation_case.answer_option_id or "unavailable",
                expected,
            ]
            if v4_summary is not None:
                values.append(evaluation_case.label_provenance or "unavailable")
                legacy_labels = [
                    f"{question}: {ids} ({provenance}; {', '.join(reasons)})"
                    for question, ids, provenance, reasons in zip(
                        evaluation_case.legacy_question_ids,
                        evaluation_case.legacy_expected_option_ids,
                        evaluation_case.legacy_label_provenances,
                        evaluation_case.legacy_exclusion_reasons,
                        strict=True,
                    )
                ]
                values.append("; ".join(legacy_labels) or "none")
            values.append(
                evaluation_case.correct if evaluation_case.correct is not None else "not scored"
            )
            if v4_summary is not None:
                classification_case = classifications[evaluation_case.case_id]
                values.append(
                    classification_case.strict_correct
                    if classification_case.strict_correct is not None
                    else "excluded"
                )
                if v4_summary.category_only is not None:
                    assert classification_case.category_only is not None
                    category = classification_case.category_only
                    values.extend(
                        (
                            category.source,
                            category.option_id or "unavailable",
                            category.correct if category.correct is not None else "not scored",
                        )
                    )
            values.append(detail)
            lines.append("| " + " | ".join(_inline(value) for value in values) + " |")
        image_cases = tuple(case for case in evaluation.cases if case.selected_images)
        if image_cases:
            lines += [
                "",
                "### Prepared image treatments",
                "",
                "| Case | Image | Asset | Source hash | Prepared hash | Dimensions | Policy |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for case in image_cases:
                for image in case.selected_images:
                    asset = image.asset
                    lines.append(
                        "| "
                        + " | ".join(
                            _inline(value)
                            for value in (
                                case.case_id,
                                image.name,
                                asset.id,
                                asset.source.content_hash,
                                asset.prepared.content_hash,
                                f"{asset.source.width}x{asset.source.height} -> "
                                f"{asset.prepared.width}x{asset.prepared.height}",
                                asset.preparation.model_dump(mode="json"),
                            )
                        )
                        + " |"
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
    if content.diagnostic is not None:
        diagnostic = content.diagnostic
        diagnostic_summary = diagnostic.summary
        lines += [
            "",
            "## Diagnostic snapshot",
            "",
            f"- Group: `{_inline(diagnostic.group_id)}` ({_inline(diagnostic.group_hash)})",
            f"- Snapshot: `{_inline(diagnostic.snapshot_id)}` "
            f"({_inline(diagnostic.snapshot_hash)}), "
            f"sequence {diagnostic.snapshot_sequence}",
            f"- Segment: `{_inline(diagnostic.segment_id or 'initial')}`",
            f"- Attempt cap: {diagnostic.max_attempts}; deadline seconds: "
            f"{diagnostic.deadline_seconds}",
            f"- Selection: {_inline(diagnostic.algorithm)}, seed {_inline(diagnostic.seed)}, "
            f"requested orders {len(diagnostic.orders)}",
            f"- Independent cases: {diagnostic_summary.independent_case_count}; orders: "
            f"{diagnostic_summary.order_count}; expanded results: "
            f"{diagnostic_summary.expanded_result_count}; "
            f"fully observed cases: {diagnostic_summary.fully_observed_case_count}",
            f"- Disagreement: {_rate(diagnostic_summary.disagreement.model_dump(mode='json'))}",
            "- Interpretation: observed request order sensitivity",
            "",
        ]
        for number, member in enumerate(diagnostic.members, 1):
            lines.extend(_group_member_context(number, member))
        lines += [
            "",
            "### Per case and order",
            "",
            "| Case | Options by order | Statuses by order | Disagreement | Fully observed |",
            "| --- | --- | --- | --- | --- |",
        ]
        for diagnostic_case in diagnostic_summary.cases:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _inline(diagnostic_case.case_id),
                        _inline(diagnostic_case.option_ids),
                        _inline(diagnostic_case.statuses),
                        _inline(diagnostic_case.observed_disagreement),
                        _inline(diagnostic_case.fully_observed),
                    )
                )
                + " |"
            )
    if content.check is not None:
        check = content.check
        lines += [
            "",
            "## Regression check snapshot",
            "",
            f"- Group: `{_inline(check.group_id)}` ({_inline(check.group_hash)})",
            f"- Snapshot: `{_inline(check.snapshot_id)}` ({_inline(check.snapshot_hash)}), "
            f"sequence {check.snapshot_sequence}",
            f"- Segment: `{_inline(check.segment_id or 'initial')}`",
            f"- Attempt cap: {check.max_attempts}; deadline seconds: {check.deadline_seconds}",
            f"- Baseline: {_inline(check.baseline_unavailable)}",
            f"- Expectation failures: {check.expectation_failures}",
            "",
        ]
        for number, member in enumerate(check.members, 1):
            lines.extend(_group_member_context(number, member))
        lines += [
            "",
            "### Frozen regression outcomes",
            "",
            "| Regression | Original hash | Case | Expected | Actual | Pass | Status | "
            "Provenance | Split | Reason |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for check_case in check.cases:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _inline(check_case.regression_id),
                        _inline(check_case.regression_hash),
                        _inline(check_case.case_id),
                        _inline(check_case.expected_option_ids),
                        _inline(check_case.actual_option_id or "unavailable"),
                        _inline(
                            check_case.passed if check_case.passed is not None else "unavailable"
                        ),
                        _inline(check_case.status),
                        _inline(check_case.provenance),
                        _inline(check_case.original_split),
                        _inline(check_case.reason),
                    )
                )
                + " |"
            )
        lines += ["", "### Regression source lineage", ""]
        for check_case in check.cases:
            lines.append(
                f"- Regression `{_inline(check_case.regression_id)}` original input hash "
                f"`{check_case.input_hash}`; source run "
                f"`{_inline(check_case.source_run_id or 'unavailable')}`, result "
                f"`{_inline(check_case.source_result_snapshot_id or 'unavailable')}`, attempt "
                f"`{_inline(check_case.source_attempt_id or 'unavailable')}`."
            )
    if content.diagnostic is not None or content.check is not None:
        lines += [
            "",
            "## Frozen source context",
            "",
            f"- Evaluations: {_inline(', '.join(target.evaluation_ids) or 'none')}",
            f"- Results: {_inline(', '.join(target.result_snapshot_ids) or 'none')}",
            f"- Labels: {_inline(', '.join(target.label_snapshot_ids) or 'none')}",
        ]
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
                source = item.source.replace("\r\n", "\n").replace("\r", "\n")
                longest = max(
                    (len(match.group(0)) for match in re.finditer(r"`+", source)), default=0
                )
                fence = "`" * max(3, longest + 1)
                lines.extend((fence, source, fence))
    return "\n".join(lines).rstrip("\n") + "\n"


def render_content(
    record: ReportRecord, content: ReportContent, format: ReportFormat
) -> RenderedArtifact:
    if format not in ("json", "markdown", "csv"):
        raise ValueError("invalid_report_format")
    if format == "json":
        parsed = parse_json(record.content_source, REPORT_CONTENT_LIMITS)
        envelope: JsonValue = {
            "schema_version": 1,
            "report_id": record.id,
            "created_at": record.created_at,
            "content_hash": record.content_hash,
            "content": parsed,
        }
        body = (dump_json(envelope, sort_keys=True, limits=REPORT_RECORD_LIMITS) + "\n").encode(
            "utf-8", "strict"
        )
    elif format == "csv":
        from deykit.reports.classification_render import classification_csv

        body = classification_csv(record, content)
    else:
        body = _markdown(record, content).encode("utf-8", "strict")
    if len(body) > REPORT_ARTIFACT_MAX_BYTES:
        raise ValueError("report_artifact_limit")
    return RenderedArtifact(record.id, format, body, hashlib.sha256(body).hexdigest(), len(body))
