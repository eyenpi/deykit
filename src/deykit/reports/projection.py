"""Pure projection of admitted immutable evaluation evidence."""

from __future__ import annotations

import base64
from decimal import Decimal
from typing import cast

from deykit.application.dataset_support import fail
from deykit.application.evaluation_evidence import snapshot_attempts
from deykit.application.evaluations import (
    EvaluationView,
    FrozenEvaluation,
    frozen_evaluation_from_records,
)
from deykit.comparisons.models import (
    ComparedCase,
    ComparisonCaseSide,
    ComparisonContext,
    ComparisonOutcomes,
)
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.json_value import JsonError, JsonValue, bytes_hash, dump_json, parse_json
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import PreparedCase
from deykit.contracts.redaction import Sanitizer, safe_choice_response
from deykit.metrics import assess_results
from deykit.reports.models import (
    AttemptEvidence,
    EvaluationMetrics,
    RawChoices,
    RawMaterial,
    ReportCase,
    ReportContent,
    ReportEvaluation,
    ReportMetadata,
    RunEvidenceContext,
)


def _safe_text(sanitizer: Sanitizer, value: str | None) -> str | None:
    if value is None:
        return None
    safe = sanitizer.text(value)
    return safe


def _safe_identity(sanitizer: Sanitizer, value: str) -> str:
    if sanitizer.text(value) != value:
        fail("report_sensitive_identity", "validation_error")
    return value


def project_opaque_response_bytes(
    value: bytes,
    *,
    run_id: str,
    case_id: str,
    attempt_id: str | None,
    sanitizer: Sanitizer,
) -> RawMaterial:
    """Project admitted opaque bytes while retaining exact source and sanitized hashes."""
    sanitized = sanitizer.bytes(value)
    try:
        source = sanitized.decode("utf-8", "strict")
        encoding = "utf8"
    except UnicodeDecodeError:
        source = base64.b64encode(sanitized).decode("ascii")
        encoding = "base64"
    return RawMaterial(
        category="response",
        run_id=run_id,
        case_id=case_id,
        attempt_id=attempt_id,
        encoding=encoding,
        source=source,
        identity_kind="stored_response_bytes_hash",
        original_hash=bytes_hash(value),
        sanitized_hash=bytes_hash(sanitized),
        changed_by_redaction=sanitized != value,
    )


def _record_version_is_explicit(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    version = value.get("schema_version")
    return isinstance(version, Decimal) and version == 1 and version.as_tuple().exponent == 0


def _safe_error(error: ServiceError | None, sanitizer: Sanitizer) -> JsonValue:
    if error is None:
        return None
    for identity in (error.resource_id, error.reason):
        if identity is not None:
            _safe_identity(sanitizer, identity)
    return cast(JsonValue, error.model_dump(mode="json"))


def _validate_response_identities(original: JsonValue, safe: JsonValue) -> None:
    if not isinstance(original, dict) or not isinstance(safe, dict):
        return
    original_answers = original.get("answers")
    safe_answers = safe.get("answers")
    if not isinstance(original_answers, dict) or not isinstance(safe_answers, dict):
        return
    if set(original_answers) != set(safe_answers):
        fail("report_sensitive_identity", "validation_error")
    for question_id, original_answer in original_answers.items():
        safe_answer = safe_answers[question_id]
        if not isinstance(original_answer, dict) or not isinstance(safe_answer, dict):
            continue
        for field in ("question_id", "option_id"):
            original_id = original_answer.get(field)
            if isinstance(original_id, str) and safe_answer.get(field) != original_id:
                fail("report_sensitive_identity", "validation_error")
        probabilities = original_answer.get("probabilities")
        safe_probabilities = safe_answer.get("probabilities")
        if isinstance(probabilities, dict) and isinstance(safe_probabilities, dict):
            if set(probabilities) != set(safe_probabilities):
                fail("report_sensitive_identity", "validation_error")


def safe_comparison_outcomes(
    outcomes: ComparisonOutcomes, sanitizer: Sanitizer
) -> ComparisonOutcomes:
    """Keep P11 classifications/identities exact while sanitizing display text."""
    contexts: list[ComparisonContext] = []
    for context in (outcomes.left, outcomes.right):
        for name, value in context.model_dump(mode="python").items():
            if name in {"requested_model", "answering_models", "compiler_version"}:
                continue
            if isinstance(value, str):
                _safe_identity(sanitizer, value)
            elif isinstance(value, tuple):
                for item in value:
                    if isinstance(item, str):
                        _safe_identity(sanitizer, item)
        contexts.append(
            context.model_copy(
                update={
                    "requested_model": sanitizer.text(context.requested_model),
                    "answering_models": tuple(
                        sorted({sanitizer.text(item) for item in context.answering_models})
                    ),
                    "compiler_version": sanitizer.text(context.compiler_version),
                }
            )
        )
    cases: list[ComparedCase] = []
    for case in outcomes.cases:
        _safe_identity(sanitizer, case.case_id)
        sides: dict[str, ComparisonCaseSide | None] = {}
        for side_name in ("left", "right"):
            side = getattr(case, side_name)
            if side is not None:
                _safe_identity(sanitizer, side.input_hash)
                if side.request_hash is not None:
                    _safe_identity(sanitizer, side.request_hash)
                for identity in side.expected_option_ids:
                    _safe_identity(sanitizer, identity)
                sides[side_name] = side.model_copy(
                    update={
                        "label_provenance": _safe_text(sanitizer, side.label_provenance),
                        "exclusion_reasons": tuple(
                            sanitizer.text(item) for item in side.exclusion_reasons
                        ),
                    }
                )
            else:
                sides[side_name] = None
        cases.append(case.model_copy(update=sides))

    def safe_counts(counts: dict[str, int]) -> dict[str, int]:
        safe: dict[str, int] = {}
        for key, count in counts.items():
            display = sanitizer.text(key)
            safe[display] = safe.get(display, 0) + count
        return safe

    safe = outcomes.model_copy(
        update={
            "left": contexts[0],
            "right": contexts[1],
            "cases": tuple(cases),
            "left_exclusion_counts": safe_counts(outcomes.left_exclusion_counts),
            "right_exclusion_counts": safe_counts(outcomes.right_exclusion_counts),
        }
    )
    try:
        from deykit.contracts.model_admission import admit_model

        return admit_model(ComparisonOutcomes, safe, "report_comparison_mismatch")
    except ValueError:
        fail("report_comparison_mismatch", "incompatible_data")


def sanitizer_would_change(content: ReportContent, sanitizer: Sanitizer) -> bool:
    for evaluation in content.evaluations:
        context = evaluation.context
        displays = (
            context.requested_model,
            *context.answering_models,
            context.compiler_version,
        )
        if any(sanitizer.text(item) != item for item in displays):
            return True
        for case in evaluation.cases:
            for value in (
                case.native_confidence_semantics,
                case.reported_model,
                case.label_provenance,
            ):
                if value is not None and sanitizer.text(value) != value:
                    return True
        if any(
            sanitizer.text(item.requested_model) != item.requested_model
            for item in evaluation.attempts
        ):
            return True
    if content.comparison is not None:
        if safe_comparison_outcomes(content.comparison, sanitizer) != content.comparison:
            return True
    for item in content.raw_material:
        if item.source is None:
            continue
        if item.encoding == "json_source_utf8":
            try:
                parsed = parse_json(item.source)
                sanitized = (
                    safe_choice_response(parsed, sanitizer)
                    if item.category == "response"
                    else sanitizer.value(parsed)
                )
                if sanitized != parsed:
                    return True
            except JsonError:
                if sanitizer.text(item.source) != item.source:
                    return True
        elif sanitizer.text(item.source) != item.source:
            return True
    return False


def validate_report_identity_context(
    report_id: str, content_hash: str, content: ReportContent, sanitizer: Sanitizer
) -> None:
    """Reject sanitized authoritative IDs and hashes without rewriting evidence."""
    identities: list[str] = [report_id, content_hash]
    target = content.target
    identities.extend(
        (
            target.target_id,
            *target.evaluation_ids,
            *target.result_snapshot_ids,
            *target.label_snapshot_ids,
        )
    )
    if target.comparison_id is not None:
        identities.append(target.comparison_id)
    if target.comparison_hash is not None:
        identities.append(target.comparison_hash)
    for evaluation in content.evaluations:
        context = evaluation.context
        identities.extend(
            (
                context.run_id,
                context.manifest_hash,
                context.decision_id,
                context.decision_revision_id,
                context.definition_hash,
                context.dataset_id,
                context.dataset_snapshot_id,
                context.dataset_hash,
                context.label_snapshot_id,
                context.label_hash,
                context.result_snapshot_id,
                context.result_hash,
                context.evaluation_id,
                context.evaluation_hash,
                context.provider_profile_id,
                context.provider_config_hash,
                *context.compiler_ids,
                context.question_id,
                *context.option_ids,
                *context.option_order,
                *context.selected_case_ids,
                context.baseline_dataset_snapshot_id,
                context.baseline_dataset_hash,
                context.baseline_label_snapshot_id,
                context.baseline_label_hash,
                context.adapter,
            )
        )
        if context.fixture_set_id is not None:
            identities.append(context.fixture_set_id)
        metrics = evaluation.metrics
        identities.extend(
            (
                metrics.run_id,
                metrics.decision_id,
                metrics.decision_revision_id,
                metrics.dataset_id,
                metrics.dataset_snapshot_id,
                metrics.result_snapshot_id,
                metrics.label_snapshot_id,
                *metrics.summary.option_ids,
                *(item.option_id for item in metrics.summary.classes),
                metrics.baseline.fit_dataset_snapshot_id,
                metrics.baseline.fit_label_snapshot_id,
                metrics.baseline.evaluation_dataset_snapshot_id,
                metrics.baseline.evaluation_label_snapshot_id,
                *metrics.baseline.overlap_case_ids,
            )
        )
        if metrics.baseline.option_id is not None:
            identities.append(metrics.baseline.option_id)
        for case in evaluation.cases:
            identities.append(case.case_id)
            identities.append(case.input_hash)
            for value in (
                case.attempt_id,
                case.answer_question_id,
                case.answer_option_id,
            ):
                if value is not None:
                    identities.append(value)
            identities.extend(case.expected_option_ids)
            identities.extend(case.legacy_question_ids)
            for expected_ids in case.legacy_expected_option_ids:
                identities.extend(expected_ids)
            if case.error is not None:
                if case.error.resource_id is not None:
                    identities.append(case.error.resource_id)
                if case.error.reason is not None:
                    identities.append(case.error.reason)
        for attempt in evaluation.attempts:
            identities.extend(
                (
                    attempt.run_id,
                    attempt.case_id,
                    attempt.attempt_id,
                    attempt.compiler,
                    attempt.adapter,
                    attempt.body_hash,
                )
            )
            if attempt.prior_attempt_id is not None:
                identities.append(attempt.prior_attempt_id)
            if attempt.error is not None:
                if attempt.error.resource_id is not None:
                    identities.append(attempt.error.resource_id)
                if attempt.error.reason is not None:
                    identities.append(attempt.error.reason)
    for item in content.raw_material:
        identities.extend((item.run_id, item.case_id))
        if item.attempt_id is not None:
            identities.append(item.attempt_id)
        if item.original_hash is not None:
            identities.append(item.original_hash)
        if item.sanitized_hash is not None:
            identities.append(item.sanitized_hash)
    if content.comparison is not None:
        for comparison_context in (content.comparison.left, content.comparison.right):
            identities.extend(
                (
                    comparison_context.evaluation_id,
                    comparison_context.evaluation_hash,
                    comparison_context.run_id,
                    comparison_context.decision_id,
                    comparison_context.decision_revision_id,
                    comparison_context.definition_hash,
                    comparison_context.dataset_id,
                    comparison_context.dataset_snapshot_id,
                    comparison_context.dataset_hash,
                    comparison_context.label_snapshot_id,
                    comparison_context.label_hash,
                    comparison_context.result_snapshot_id,
                    comparison_context.result_hash,
                    comparison_context.adapter,
                    *comparison_context.compiler_ids,
                    comparison_context.provider_profile_id,
                    comparison_context.provider_config_hash,
                    comparison_context.question_id,
                    *comparison_context.option_ids,
                    *comparison_context.option_order,
                    *comparison_context.selected_case_ids,
                )
            )
        for compared_case in content.comparison.cases:
            identities.append(compared_case.case_id)
            for side in (compared_case.left, compared_case.right):
                if side is None:
                    continue
                identities.append(side.input_hash)
                if side.request_hash is not None:
                    identities.append(side.request_hash)
                if side.answer_option_id is not None:
                    identities.append(side.answer_option_id)
                identities.extend(side.expected_option_ids)
    for identity in identities:
        _safe_identity(sanitizer, identity)


def validate_report_metadata_identities(metadata: ReportMetadata, sanitizer: Sanitizer) -> None:
    """Check every identity or hash surfaced by metadata-only read/list paths."""
    identities = [metadata.report_id, metadata.content_hash]
    for value in (
        metadata.target_id,
        metadata.comparison_id,
        metadata.diagnostic_snapshot_id,
        metadata.check_snapshot_id,
    ):
        if value is not None:
            identities.append(value)
    identities.extend(metadata.evaluation_ids)
    identities.extend(metadata.result_snapshot_ids)
    identities.extend(metadata.label_snapshot_ids)
    for identity in identities:
        _safe_identity(sanitizer, identity)


def validate_rendered_artifact_identities(
    report_id: str, artifact_hash: str, sanitizer: Sanitizer
) -> None:
    _safe_identity(sanitizer, report_id)
    _safe_identity(sanitizer, artifact_hash)


def validate_report_identity_value(identity: str, sanitizer: Sanitizer) -> None:
    _safe_identity(sanitizer, identity)


def expected_limitations(
    evaluations: tuple[ReportEvaluation, ...], raw_material: tuple[RawMaterial, ...]
) -> tuple[str, ...]:
    limitations: list[str] = []
    if any(item.metrics.evidence_mode == "fixture" for item in evaluations):
        limitations.append("authored_fixture_not_provider_quality")
    limitations.append("saved_answers_no_fresh_inference")
    if any(
        item.metrics.summary.selected_count != item.metrics.summary.status_counts.valid
        for item in evaluations
    ):
        limitations.append("partial_results")
    if any(item.metrics.summary.native_confidence_present_count for item in evaluations):
        limitations.append("native_confidence_not_calibrated")
    limitations.append("pricing_source_unavailable")
    if any(item.metrics.baseline.overlap_case_ids for item in evaluations):
        limitations.append("baseline_overlap")
    if any(item.changed_by_redaction for item in raw_material):
        limitations.append("raw_material_sanitized")
    limitations.append("unknown_plaintext_secrets_not_recognized")
    return tuple(limitations)


def _prepared(
    records: tuple[StoredRecord, ...], frozen: FrozenEvaluation
) -> tuple[PreparedCase, ...]:
    found: dict[str, PreparedCase] = {}
    expected_hashes = {item.case_id: item.input_hash for item in frozen.results.results}
    for stored in records:
        if stored.key.collection != "prepared_cases" or stored.key.scope != (frozen.manifest.id,):
            continue
        try:
            item = load_record(PreparedCase, stored.body)
        except JsonError:
            fail("report_context_mismatch", "incompatible_data")
        if (
            item.id != stored.key.resource_id
            or item.case_id != stored.key.resource_id
            or item.run_id != frozen.manifest.id
            or item.case_id not in frozen.manifest.case_ids
            or item.case_id in found
            or item.input_hash != expected_hashes.get(item.case_id)
            or (
                item.request is not None
                and (
                    item.request.compiler_version != frozen.manifest.compiler_version
                    or item.request.adapter != frozen.manifest.adapter
                    or item.request.requested_model != frozen.manifest.requested_model
                )
            )
        ):
            fail("report_context_mismatch", "incompatible_data")
        found[item.case_id] = item
    if tuple(found) != frozen.manifest.case_ids:
        # Storage iteration order is not authoritative; compare membership then order explicitly.
        if set(found) != set(frozen.manifest.case_ids):
            fail("report_context_mismatch", "incompatible_data")
    return tuple(found[case_id] for case_id in frozen.manifest.case_ids)


def project_evaluation(
    records: tuple[StoredRecord, ...], view: EvaluationView, sanitizer: Sanitizer, raw: RawChoices
) -> tuple[ReportEvaluation, tuple[RawMaterial, ...]]:
    frozen = frozen_evaluation_from_records(
        records,
        view.record.run_id,
        view.record.result_snapshot_id,
        view.record.label_snapshot_id,
        view.record.mode,
    )
    prepared = _prepared(records, frozen)
    prepared_by_case = {item.case_id: item for item in prepared}
    definition = frozen.revision.definition
    summary = assess_results(
        definition, frozen.dataset, frozen.labels, frozen.results, frozen.manifest.case_ids
    )
    cases_by_id = {case.id: case for case in frozen.dataset.cases}
    results_by_id = {item.case_id: item for item in frozen.results.results}
    assessment_by_id = {item.case_id: item for item in summary.cases}
    report_cases: list[JsonValue] = []
    raw_material: list[RawMaterial] = []
    admitted_attempts = snapshot_attempts(records, frozen.results)
    attempt_events = {event.attempt_id: event for _, event in admitted_attempts}
    for attempt, _event in admitted_attempts:
        for identity in (
            attempt.id,
            attempt.case_id,
            attempt.request.compiler,
            attempt.request.adapter,
            attempt.request.body_hash,
        ):
            _safe_identity(sanitizer, identity)

    for identity in (
        frozen.manifest.id,
        frozen.revision.id,
        frozen.revision.content_hash,
        frozen.dataset.id,
        frozen.dataset.content_hash,
        frozen.labels.id,
        frozen.labels.content_hash,
        frozen.results.id,
        frozen.results.content_hash,
        view.record.id,
        view.record.content_hash,
        frozen.manifest.provider_profile_id,
        frozen.manifest.provider_config_hash,
        frozen.baseline_dataset.id,
        frozen.baseline_dataset.content_hash,
        frozen.baseline_labels.id,
        frozen.baseline_labels.content_hash,
    ):
        _safe_identity(sanitizer, identity)

    for case_id in frozen.manifest.case_ids:
        _safe_identity(sanitizer, case_id)
        case = cases_by_id[case_id]
        result = results_by_id[case_id]
        _safe_identity(sanitizer, result.input_hash)
        if result.attempt_id is not None:
            _safe_identity(sanitizer, result.attempt_id)
        assessment = assessment_by_id[case_id]
        answer = result.answer
        if answer is not None:
            _safe_identity(sanitizer, answer.question_id)
            _safe_identity(sanitizer, answer.option_id)
        for identity in (*assessment.expected_option_ids, *assessment.legacy_question_ids):
            _safe_identity(sanitizer, identity)
        for group in assessment.legacy_expected_option_ids:
            for identity in group:
                _safe_identity(sanitizer, identity)
        safe_error = _safe_error(result.error, sanitizer)
        report_cases.append(
            {
                "case_id": case_id,
                "input_hash": result.input_hash,
                "split": case.split,
                "status": result.status,
                "attempt_id": result.attempt_id,
                "answer": None
                if answer is None
                else {
                    "question_id": answer.question_id,
                    "option_id": answer.option_id,
                    "probabilities_source": answer.probabilities_source,
                    "native_confidence_source": answer.native_confidence_source,
                    "native_confidence_semantics": _safe_text(
                        sanitizer, answer.native_confidence_semantics
                    ),
                    "reported_model": _safe_text(sanitizer, answer.reported_model),
                },
                "expected_option_ids": list(assessment.expected_option_ids),
                "label_provenance": _safe_text(sanitizer, assessment.label_provenance),
                "correct": assessment.set_correct,
                "single_label_class": assessment.single_label_class,
                "exclusion_reasons": list(assessment.exclusion_reasons),
                "legacy_question_ids": list(assessment.legacy_question_ids),
                "legacy_expected_option_ids": [
                    list(ids) for ids in assessment.legacy_expected_option_ids
                ],
                "legacy_exclusion_reasons": [
                    list(reasons) for reasons in assessment.legacy_exclusion_reasons
                ],
                "error": safe_error,
            }
        )
        if raw.inputs:
            value = parse_json(case.input_source)
            safe_value = sanitizer.value(value)
            source = (
                case.input_source if safe_value == value else dump_json(cast(JsonValue, safe_value))
            )
            raw_material.append(
                RawMaterial(
                    category="input",
                    run_id=frozen.manifest.id,
                    case_id=case_id,
                    encoding="json_source_utf8",
                    source=source,
                    identity_kind="input_semantic_hash",
                    original_hash=result.input_hash,
                    sanitized_hash=bytes_hash(source.encode("utf-8")),
                    changed_by_redaction=source != case.input_source,
                )
            )
        if raw.requests:
            prepared_case = prepared_by_case[case_id]
            request = prepared_case.request
            if request is None:
                raw_material.append(
                    RawMaterial(
                        category="request",
                        run_id=frozen.manifest.id,
                        case_id=case_id,
                        encoding=None,
                        source=None,
                        identity_kind="prepared_request_bytes_hash",
                        original_hash=None,
                        sanitized_hash=None,
                        unavailable_reason="request_not_prepared",
                    )
                )
            else:
                _safe_identity(sanitizer, request.body_hash)
                parsed = parse_json(request.body)
                safe_value = sanitizer.value(parsed)
                source = (
                    request.body.decode("utf-8")
                    if safe_value == parsed
                    else dump_json(cast(JsonValue, safe_value))
                )
                raw_material.append(
                    RawMaterial(
                        category="request",
                        run_id=frozen.manifest.id,
                        case_id=case_id,
                        attempt_id=None,
                        encoding="json_source_utf8",
                        source=source,
                        identity_kind="prepared_request_bytes_hash",
                        original_hash=request.body_hash,
                        sanitized_hash=bytes_hash(source.encode("utf-8")),
                        changed_by_redaction=source.encode("utf-8") != request.body,
                    )
                )
        if raw.responses:
            event = attempt_events.get(result.attempt_id or "")
            outcome = event.outcome if event is not None else None
            if outcome is None or outcome.raw_response_source is None:
                raw_material.append(
                    RawMaterial(
                        category="response",
                        run_id=frozen.manifest.id,
                        case_id=case_id,
                        attempt_id=result.attempt_id,
                        encoding=None,
                        source=None,
                        identity_kind="stored_response_utf8_hash",
                        original_hash=None,
                        sanitized_hash=None,
                        unavailable_reason="stored_response_unavailable",
                    )
                )
            else:
                response_hash = bytes_hash(outcome.raw_response_source.encode("utf-8"))
                _safe_identity(sanitizer, response_hash)
                value = parse_json(outcome.raw_response_source)
                safe_value = safe_choice_response(value, sanitizer)
                _validate_response_identities(value, safe_value)
                source = (
                    outcome.raw_response_source if safe_value == value else dump_json(safe_value)
                )
                raw_material.append(
                    RawMaterial(
                        category="response",
                        run_id=frozen.manifest.id,
                        case_id=case_id,
                        attempt_id=result.attempt_id,
                        encoding="json_source_utf8",
                        source=source,
                        identity_kind="stored_response_utf8_hash",
                        original_hash=bytes_hash(outcome.raw_response_source.encode("utf-8")),
                        sanitized_hash=bytes_hash(source.encode("utf-8")),
                        changed_by_redaction=source != outcome.raw_response_source,
                    )
                )

    metrics = parse_json(view.record.metrics_source)
    if not _record_version_is_explicit(metrics):
        fail("report_metrics_mismatch", "incompatible_data")
    question = definition.questions[0]
    for identity in (
        question.id,
        *(option.id for option in question.options),
        *(frozen.manifest.option_order or tuple(option.id for option in question.options)),
    ):
        _safe_identity(sanitizer, identity)
    context: JsonValue = {
        "run_id": frozen.manifest.id,
        "manifest_hash": evidence_hash((dump_record(frozen.manifest),)),
        "decision_id": frozen.manifest.decision_id,
        "decision_revision_id": frozen.revision.id,
        "definition_hash": frozen.revision.content_hash,
        "dataset_id": frozen.manifest.dataset_id,
        "dataset_snapshot_id": frozen.dataset.id,
        "dataset_hash": frozen.dataset.content_hash,
        "label_snapshot_id": frozen.labels.id,
        "label_hash": frozen.labels.content_hash,
        "result_snapshot_id": frozen.results.id,
        "result_hash": frozen.results.content_hash,
        "through_event_sequence": frozen.results.through_event_sequence,
        "evaluation_id": view.record.id,
        "evaluation_hash": view.record.content_hash,
        "evaluation_mode": view.record.mode,
        "evidence_mode": frozen.manifest.mode,
        "fixture_set_id": frozen.manifest.fixture_set_id,
        "provider_profile_id": frozen.manifest.provider_profile_id,
        "provider_config_hash": frozen.manifest.provider_config_hash,
        "adapter": frozen.manifest.adapter,
        "compiler_ids": cast(
            JsonValue,
            sorted({item.request.compiler for item in prepared if item.request is not None}),
        ),
        "compiler_version": frozen.manifest.compiler_version,
        "requested_model": _safe_text(sanitizer, frozen.manifest.requested_model),
        "answering_models": [
            _safe_text(sanitizer, model)
            for model in sorted(
                {
                    result.answer.reported_model
                    for result in frozen.results.results
                    if result.answer is not None and result.answer.reported_model is not None
                }
            )
        ],
        "question_id": question.id,
        "option_ids": [option.id for option in question.options],
        "option_order": list(
            frozen.manifest.option_order or tuple(option.id for option in question.options)
        ),
        "selected_case_ids": list(frozen.manifest.case_ids),
        "baseline_dataset_snapshot_id": frozen.baseline_dataset.id,
        "baseline_dataset_hash": frozen.baseline_dataset.content_hash,
        "baseline_label_snapshot_id": frozen.baseline_labels.id,
        "baseline_label_hash": frozen.baseline_labels.content_hash,
    }
    projected: dict[str, JsonValue] = {
        "evaluation_id": view.record.id,
        "evaluation_hash": view.record.content_hash,
        "run_id": frozen.manifest.id,
        "result_snapshot_id": frozen.results.id,
        "label_snapshot_id": frozen.labels.id,
        "evaluation_mode": view.record.mode,
        "evidence_mode": frozen.manifest.mode,
        "metrics": metrics,
        "context": context,
        "cases": report_cases,
        "attempts": [
            {
                "run_id": frozen.manifest.id,
                "case_id": attempt.case_id,
                "attempt_id": attempt.id,
                "number": attempt.number,
                "kind": attempt.kind,
                "prior_attempt_id": attempt.prior_attempt_id,
                "compiler": attempt.request.compiler,
                "adapter": attempt.request.adapter,
                "compiler_version": _safe_text(sanitizer, attempt.request.compiler_version),
                "requested_model": _safe_text(sanitizer, attempt.request.requested_model),
                "body_hash": attempt.request.body_hash,
                "state": event.state,
                "error": (
                    _safe_error(event.outcome.error, sanitizer)
                    if event.outcome is not None
                    else None
                ),
                "duration_seconds": (
                    format(event.duration_seconds, ".17g")
                    if event.duration_seconds is not None
                    else None
                ),
                "response_stored": bool(
                    event.outcome and event.outcome.raw_response_source is not None
                ),
                "usage_stored": bool(event.outcome and event.outcome.usage_source is not None),
            }
            for attempt, event in admitted_attempts
        ],
    }
    return _typed_evaluation(projected, view.record.metrics_source), tuple(raw_material)


def _typed_evaluation(projected: dict[str, JsonValue], metrics_source: str) -> ReportEvaluation:
    raw_context = projected.get("context")
    raw_cases = projected.get("cases")
    raw_attempts = projected.get("attempts")
    if (
        not isinstance(raw_context, dict)
        or not isinstance(raw_cases, list)
        or not isinstance(raw_attempts, list)
    ):
        fail("report_context_mismatch", "incompatible_data")
    raw_metrics = parse_json(metrics_source)
    if not _record_version_is_explicit(raw_metrics):
        fail("report_metrics_mismatch", "incompatible_data")
    try:
        metrics = EvaluationMetrics.model_validate_json(metrics_source, context={"persisted": True})
    except ValueError:
        fail("report_metrics_mismatch", "incompatible_data")
    report_cases: list[ReportCase] = []
    for case in raw_cases:
        if not isinstance(case, dict):
            fail("report_context_mismatch", "incompatible_data")
        answer = case.get("answer")
        answer_map = answer if isinstance(answer, dict) else {}
        report_cases.append(
            ReportCase.model_validate_json(
                dump_json(
                    {
                        "case_id": case.get("case_id"),
                        "input_hash": case.get("input_hash"),
                        "split": case.get("split"),
                        "status": case.get("status"),
                        "attempt_id": case.get("attempt_id"),
                        "answer_question_id": answer_map.get("question_id"),
                        "answer_option_id": answer_map.get("option_id"),
                        "probabilities_source": answer_map.get("probabilities_source"),
                        "native_confidence_source": answer_map.get("native_confidence_source"),
                        "native_confidence_semantics": answer_map.get(
                            "native_confidence_semantics"
                        ),
                        "reported_model": answer_map.get("reported_model"),
                        "expected_option_ids": case.get("expected_option_ids", []),
                        "label_provenance": case.get("label_provenance"),
                        "correct": case.get("correct"),
                        "single_label_class": case.get("single_label_class"),
                        "exclusion_reasons": case.get("exclusion_reasons", []),
                        "legacy_question_ids": case.get("legacy_question_ids", []),
                        "legacy_expected_option_ids": case.get("legacy_expected_option_ids", []),
                        "legacy_exclusion_reasons": case.get("legacy_exclusion_reasons", []),
                        "error": case.get("error"),
                    }
                )
            )
        )
    attempts = tuple(AttemptEvidence.model_validate(item) for item in raw_attempts)
    return ReportEvaluation(
        context=RunEvidenceContext.model_validate_json(dump_json(raw_context)),
        metrics=metrics,
        cases=tuple(report_cases),
        attempts=attempts,
    )
