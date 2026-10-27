"""Pure display projections for captured diagnostic and check snapshots."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast

from deykit.application.checks import FrozenCheckSnapshot, check_snapshot_from_records
from deykit.application.dataset_support import fail
from deykit.application.diagnostics import (
    FrozenDiagnosticSnapshot,
    diagnostic_snapshot_from_records,
)
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import FrozenEvaluation
from deykit.application.images import ImageAssets
from deykit.contracts.codec import dump_record
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.images import SelectedImage
from deykit.contracts.json_value import JsonValue, dump_json
from deykit.contracts.ports import StoredRecord
from deykit.contracts.redaction import Sanitizer
from deykit.contracts.report_json import REPORT_CONTENT_LIMITS
from deykit.diagnostics.orders import ORDER_ALGORITHM, choice_orders
from deykit.reports.models import (
    CaseImageTreatment,
    CheckCaseDisplay,
    CheckReport,
    DiagnosticCaseDisplay,
    DiagnosticOrderAnalysisDisplay,
    DiagnosticReport,
    DiagnosticSummaryDisplay,
    GroupReportContext,
    MemberEvidenceContext,
    RateDisplay,
    RawChoices,
    RawMaterial,
)
from deykit.reports.projection import _prepared, _safe_identity, project_frozen_raw_material
from deykit.runner.group_selection import decode_group_start_selection


def _member_context(
    records: tuple[StoredRecord, ...], frozen: FrozenEvaluation, sanitizer: Sanitizer
) -> MemberEvidenceContext:
    prepared = _prepared(records, frozen)
    manifest = frozen.manifest
    if manifest.decision_id is None or manifest.dataset_id is None:
        fail("report_context_mismatch", "incompatible_data")
    question = frozen.revision.definition.questions[0]
    compiler_ids = tuple(sorted({item.request.compiler for item in prepared if item.request}))
    answering_models = tuple(
        sorted(
            {
                sanitizer.text(item.answer.reported_model)
                for item in frozen.results.results
                if item.answer is not None and item.answer.reported_model is not None
            }
        )
    )
    order = manifest.option_order or tuple(option.id for option in question.options)
    identities = (
        manifest.id,
        evidence_hash((dump_record(manifest),)),
        manifest.decision_id,
        frozen.revision.id,
        frozen.revision.content_hash,
        manifest.dataset_id,
        frozen.dataset.id,
        frozen.dataset.content_hash,
        frozen.labels.id,
        frozen.labels.content_hash,
        frozen.results.id,
        frozen.results.content_hash,
        manifest.provider_profile_id,
        manifest.provider_config_hash,
        manifest.adapter,
        *compiler_ids,
        question.id,
        *(option.id for option in question.options),
        *order,
        *manifest.case_ids,
        frozen.baseline_dataset.id,
        frozen.baseline_dataset.content_hash,
        frozen.baseline_labels.id,
        frozen.baseline_labels.content_hash,
    )
    for identity in identities:
        _safe_identity(sanitizer, identity)
    image_treatments = []
    image_assets = ImageAssets({record.key: record for record in records})
    for case in frozen.dataset.cases:
        if not frozen.revision.definition.selected_images:
            break
        assets = image_assets.for_case(case)
        images = tuple(
            SelectedImage(name=name, asset=assets[name].identity())
            for name in frozen.revision.definition.selected_images
        )
        for image in images:
            for identity in (
                image.name,
                image.asset.id,
                image.asset.source.content_hash,
                image.asset.prepared.content_hash,
            ):
                _safe_identity(sanitizer, identity)
        image_treatments.append(CaseImageTreatment(case_id=case.id, selected_images=images))
    return MemberEvidenceContext(
        run_id=manifest.id,
        manifest_hash=evidence_hash((dump_record(manifest),)),
        decision_id=manifest.decision_id,
        decision_revision_id=frozen.revision.id,
        definition_hash=frozen.revision.content_hash,
        dataset_id=manifest.dataset_id,
        dataset_snapshot_id=frozen.dataset.id,
        dataset_hash=frozen.dataset.content_hash,
        label_snapshot_id=frozen.labels.id,
        label_hash=frozen.labels.content_hash,
        result_snapshot_id=frozen.results.id,
        result_hash=frozen.results.content_hash,
        through_event_sequence=frozen.results.through_event_sequence,
        evidence_mode=manifest.mode,
        fixture_set_id=manifest.fixture_set_id,
        provider_profile_id=manifest.provider_profile_id,
        provider_config_hash=manifest.provider_config_hash,
        adapter=manifest.adapter,
        compiler_ids=compiler_ids,
        compiler_version=sanitizer.text(manifest.compiler_version),
        requested_model=sanitizer.text(manifest.requested_model),
        answering_models=answering_models,
        question_id=question.id,
        option_ids=tuple(option.id for option in question.options),
        option_order=order,
        selected_case_ids=manifest.case_ids,
        image_treatments=tuple(image_treatments),
        baseline_dataset_snapshot_id=frozen.baseline_dataset.id,
        baseline_dataset_hash=frozen.baseline_dataset.content_hash,
        baseline_label_snapshot_id=frozen.baseline_labels.id,
        baseline_label_hash=frozen.baseline_labels.content_hash,
    )


def _group_context(
    records: tuple[StoredRecord, ...],
    frozen: FrozenDiagnosticSnapshot | FrozenCheckSnapshot,
    sanitizer: Sanitizer,
) -> GroupReportContext:
    if frozen.group.kind == "experiment":
        fail("report_context_mismatch", "incompatible_data")
    segment_id = frozen.segment.id if frozen.segment is not None else None
    for identity in (
        frozen.group.id,
        frozen.group.content_hash,
        frozen.snapshot.id,
        frozen.snapshot.content_hash,
        *((segment_id,) if segment_id is not None else ()),
    ):
        _safe_identity(sanitizer, identity)
    return GroupReportContext(
        group_id=frozen.group.id,
        group_hash=frozen.group.content_hash,
        group_kind=frozen.group.kind,
        max_attempts=frozen.group.max_attempts,
        deadline_seconds=frozen.group.deadline_seconds,
        snapshot_id=frozen.snapshot.id,
        snapshot_hash=frozen.snapshot.content_hash,
        snapshot_sequence=frozen.snapshot.sequence,
        segment_id=segment_id,
        members=tuple(_member_context(records, item, sanitizer) for item in frozen.members),
    )


def _selection(frozen: FrozenDiagnosticSnapshot) -> tuple[int, str, tuple[tuple[str, ...], ...]]:
    try:
        source = decode_group_start_selection(
            frozen.group.selection_source, expected_kind="choice_order"
        ).original_selection
        if (
            not isinstance(source, dict)
            or set(source) != {"kind", "request"}
            or source.get("kind") != "choice_order"
            or not isinstance(source.get("request"), dict)
        ):
            fail("report_group_selection_mismatch", "incompatible_data")
        request_source = cast(dict[str, JsonValue], source["request"])
        if set(request_source) - {"run", "orders", "seed"} or not isinstance(
            request_source.get("run"), dict
        ):
            fail("report_group_selection_mismatch", "incompatible_data")
        raw_orders = request_source.get("orders", 4)
        raw_seed = request_source.get("seed", 0)
        orders = _exact_bounded_integer(raw_orders, minimum=1, maximum=4)
        seed = _exact_bounded_integer(raw_seed, minimum=-(2**63), maximum=(2**63) - 1)
    except (ServiceFailure, ValueError):
        fail("report_group_selection_mismatch", "incompatible_data")
    if not frozen.members:
        fail("report_group_selection_mismatch", "incompatible_data")
    member_orders = tuple(member.manifest.option_order for member in frozen.members)
    option_ids = tuple(
        option.id for option in frozen.members[0].revision.definition.questions[0].options
    )
    try:
        expected_orders = choice_orders(option_ids, orders=orders, seed=seed)
    except ValueError:
        fail("report_group_selection_mismatch", "incompatible_data")
    if (
        any(order is None for order in member_orders)
        or cast(tuple[tuple[str, ...], ...], member_orders) != expected_orders
    ):
        fail("report_group_selection_mismatch", "incompatible_data")
    return seed, ORDER_ALGORITHM, expected_orders


def _exact_bounded_integer(value: JsonValue, *, minimum: int, maximum: int) -> int:
    if type(value) is int:
        if minimum <= value <= maximum:
            return value
        fail("report_group_selection_mismatch", "incompatible_data")
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value() and minimum <= value <= maximum:
            return int(value)
    fail("report_group_selection_mismatch", "incompatible_data")


def project_diagnostic(
    records: tuple[StoredRecord, ...],
    frozen: FrozenDiagnosticSnapshot,
    sanitizer: Sanitizer,
    *,
    include_order_analysis: bool = True,
) -> DiagnosticReport:
    context = _group_context(records, frozen, sanitizer)
    seed, algorithm, orders = _selection(frozen)
    summary_source = frozen.summary.source()
    cases_source = summary_source.get("cases")
    if not isinstance(cases_source, list):
        fail("report_diagnostic_mismatch", "incompatible_data")
    cases: list[DiagnosticCaseDisplay] = []
    for case in cases_source:
        if not isinstance(case, dict):
            fail("report_diagnostic_mismatch", "incompatible_data")
        cases.append(DiagnosticCaseDisplay.model_validate_json(dump_json(cast(JsonValue, case))))
    disagreement_source = summary_source.get("disagreement")
    if not isinstance(disagreement_source, dict):
        fail("report_diagnostic_mismatch", "incompatible_data")
    analysis_source = summary_source.get("order_analysis")
    if include_order_analysis and not isinstance(analysis_source, dict):
        fail("report_diagnostic_mismatch", "incompatible_data")
    summary = DiagnosticSummaryDisplay(
        independent_case_count=frozen.summary.independent_case_count,
        order_count=frozen.summary.order_count,
        expanded_result_count=frozen.summary.expanded_result_count,
        fully_observed_case_count=frozen.summary.fully_observed_case_count,
        disagreement=RateDisplay.model_validate(disagreement_source),
        cases=tuple(cases),
        interpretation="observed_request_order_sensitivity",
        order_analysis=(
            DiagnosticOrderAnalysisDisplay.model_validate_json(
                dump_json(analysis_source, limits=REPORT_CONTENT_LIMITS)
            )
            if include_order_analysis and isinstance(analysis_source, dict)
            else None
        ),
    )
    return DiagnosticReport(
        **context.model_dump(mode="python", exclude={"group_kind"}),
        group_kind="choice_order",
        seed=seed,
        algorithm=algorithm,
        orders=orders,
        summary=summary,
    )


def project_check(
    records: tuple[StoredRecord, ...], frozen: FrozenCheckSnapshot, sanitizer: Sanitizer
) -> CheckReport:
    context = _group_context(records, frozen, sanitizer)
    regression_by_id = {item.id: item for item in frozen.regressions}
    if len(regression_by_id) != len(frozen.regressions):
        fail("report_check_mismatch", "incompatible_data")
    cases: list[CheckCaseDisplay] = []
    for case in frozen.cases:
        regression = regression_by_id.get(case.regression_id)
        if regression is None or regression.content_hash is None:
            fail("report_check_mismatch", "incompatible_data")
        for identity in (
            case.regression_id,
            regression.content_hash,
            case.dataset_id,
            case.case_id,
            case.run_id,
            case.result_snapshot_id,
            *case.expected_option_ids,
            case.input_hash,
            *(
                value
                for value in (
                    case.source_run_id,
                    case.source_result_snapshot_id,
                    case.source_attempt_id,
                )
                if value is not None
            ),
        ):
            _safe_identity(sanitizer, identity)
        cases.append(
            CheckCaseDisplay(
                regression_id=case.regression_id,
                regression_hash=regression.content_hash,
                dataset_id=case.dataset_id,
                case_id=case.case_id,
                run_id=case.run_id,
                result_snapshot_id=case.result_snapshot_id,
                status=case.status,
                expected_option_ids=case.expected_option_ids,
                actual_option_id=case.actual_option_id,
                passed=case.passed,
                provenance=sanitizer.text(case.provenance),
                original_split=cast(
                    Literal["development", "calibration", "test"], case.original_split
                ),
                input_hash=case.input_hash,
                source_run_id=case.source_run_id,
                source_result_snapshot_id=case.source_result_snapshot_id,
                source_attempt_id=case.source_attempt_id,
                reason=sanitizer.text(case.reason),
            )
        )
    return CheckReport(
        **context.model_dump(mode="python", exclude={"group_kind"}),
        group_kind="regression_check",
        cases=tuple(cases),
        expectation_failures=frozen.expectation_failures,
        baseline_unavailable=frozen.baseline_unavailable,
    )


def project_group_raw(
    records: tuple[StoredRecord, ...],
    frozen: FrozenDiagnosticSnapshot | FrozenCheckSnapshot,
    sanitizer: Sanitizer,
    raw: RawChoices,
) -> tuple[RawMaterial, ...]:
    return tuple(
        item
        for member in frozen.members
        for item in project_frozen_raw_material(records, member, sanitizer, raw)
    )


def read_diagnostic(
    records: tuple[StoredRecord, ...], snapshot_id: str
) -> FrozenDiagnosticSnapshot:
    return diagnostic_snapshot_from_records(records, snapshot_id)


def read_check(records: tuple[StoredRecord, ...], snapshot_id: str) -> FrozenCheckSnapshot:
    return check_snapshot_from_records(records, snapshot_id)
