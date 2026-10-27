"""Aggregate one pinned experiment snapshot without writing or calling providers."""

from collections import Counter
from dataclasses import dataclass

from deykit.application.dataset_support import decoded, fail, identifier
from deykit.application.evaluations import (
    FrozenEvaluation,
    frozen_evaluation_from_records,
    metrics_from_frozen,
)
from deykit.application.experiment_reuse import admit_reuse, reuse_members
from deykit.contracts.execution_groups import ExperimentReuse, ExperimentSnapshot
from deykit.contracts.experiments import ExperimentOrder, amount_text
from deykit.contracts.json_value import JsonValue
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.redaction import Sanitizer
from deykit.diagnostics.summary import summarize_orders
from deykit.metrics import assess_results
from deykit.metrics.summary import Rate
from deykit.runner.decoding import HistoryDecoder
from deykit.runner.experiment_plan import ExperimentMember, diagnostic_base_index
from deykit.runner.group_evidence import (
    admit_group_snapshots,
    experiment_members,
    experiment_request,
    group_budget,
)
from deykit.runner.history import history_from_records


@dataclass(frozen=True)
class ExperimentReportMember:
    member: ExperimentMember
    run_id: str
    result_snapshot_id: str
    evidence_mode: str
    provider_profile_id: str
    adapter: str
    requested_model: str
    reported_model_counts: dict[str, int]
    unknown_reported_model_answers: int
    provider_config_hash: str
    selected_cases: int
    status_counts: dict[str, int]
    applicable_expectations: int
    excluded_expectations: int
    applicable_label_provenance: dict[str, int]
    excluded_label_provenance: dict[str, int]
    exclusion_counts: dict[str, int]
    full_cohort_strict_accuracy: dict[str, JsonValue]
    valid_answer_accuracy: dict[str, JsonValue]
    attempts_reserved: int
    reserved_usd: str | None
    source_attempts_reserved: int
    source_reserved_usd: str | None
    usage: JsonValue
    latency: JsonValue


@dataclass(frozen=True)
class ExperimentDiagnosticReport:
    name: str
    kind: str
    independent_cases: int
    planned_fresh_requests: int
    valid_fresh_answers: int
    fully_observed_cases: int
    excluded_cases: int
    disagreement: dict[str, JsonValue]


@dataclass(frozen=True)
class ExperimentReport:
    experiment_id: str
    source_group_id: str
    snapshot_id: str
    reused: bool
    attempts_reserved: int
    reserved_usd: str
    unknown_price_attempts: int
    billed_cost_usd: None
    members: tuple[ExperimentReportMember, ...]
    diagnostics: tuple[ExperimentDiagnosticReport, ...]


def experiment_report(
    records: tuple[StoredRecord, ...], experiment_id: str, snapshot_id: str | None = None
) -> ExperimentReport:
    identifier(experiment_id)
    if snapshot_id is not None:
        identifier(snapshot_id)
    reuse_stored = next(
        (r for r in records if r.key == ResourceKey("experiment_reuses", experiment_id)), None
    )
    reuse = decoded(ExperimentReuse, reuse_stored) if reuse_stored else None
    if reuse:
        admit_reuse(records, reuse)
        if snapshot_id is not None and snapshot_id != reuse.source_snapshot_id:
            fail("experiment_reuse_snapshot_mismatch", "validation_error")
        snapshot_id = reuse.source_snapshot_id
    group_id = reuse.source_group_id if reuse else experiment_id
    decoder = HistoryDecoder()
    budget = group_budget(records, group_id, decoder=decoder)
    if budget.group.kind != "experiment":
        fail("experiment_group_required")
    snapshots = admit_group_snapshots(records, group_id, decoder=decoder)
    selected = (
        next((item for item in snapshots if item.id == snapshot_id), None)
        if snapshot_id
        else snapshots[-1]
        if snapshots
        else None
    )
    if not isinstance(selected, ExperimentSnapshot):
        fail("experiment_snapshot_missing", "not_found")
    prices = dict(budget.member_prices)
    output = []
    frozen_members = []
    planned_members = []
    sanitizer = Sanitizer()
    reserved_units = unknown_prices = attempts = 0
    specs = reuse_members(reuse) if reuse else experiment_members(budget.group, records)
    for member, spec in zip(selected.results, specs, strict=True):
        history = history_from_records(records, member.run_id, verify_group=False, decoder=decoder)
        frozen = frozen_evaluation_from_records(
            records,
            member.run_id,
            member.result_snapshot_id,
            None,
            "original",
            decoder=decoder,
            history=history,
        )
        frozen_members.append(frozen)
        summary = assess_results(
            frozen.revision.definition,
            frozen.dataset,
            frozen.labels,
            frozen.results,
            frozen.manifest.case_ids,
        )
        answer_exclusions = {
            "no_valid_answer",
            "incompatible_answer",
            "acceptable_set_excluded_from_class_metrics",
        }
        applicable = tuple(
            case
            for case in summary.cases
            if case.expected_option_ids and not (set(case.exclusion_reasons) - answer_exclusions)
        )
        correct = sum(case.set_correct is True for case in applicable)
        valid = sum(case.set_correct is not None for case in applicable)
        metrics = metrics_from_frozen(frozen, "original")
        planned_members.append(sum(item.request is not None for item in history.prepared))
        applicable_ids = {case.case_id for case in applicable}
        applicable_provenance = dict(
            Counter(case.label_provenance or "unlabelled" for case in applicable)
        )
        excluded_provenance = dict(
            Counter(
                case.label_provenance or "unlabelled"
                for case in summary.cases
                if case.case_id not in applicable_ids
            )
        )
        member_attempts = sum(
            event.state == "attempt_reserved"
            and event.sequence <= frozen.results.through_event_sequence
            for event in history.events
        )
        price = prices[member.run_id]
        member_units = member_attempts * price if price is not None else None
        answering_models = Counter(
            sanitizer.text(item.answer.reported_model)
            for item in frozen.results.results
            if item.answer is not None and item.answer.reported_model is not None
        )
        unknown_models = sum(
            item.answer is not None and item.answer.reported_model is None
            for item in frozen.results.results
        )
        attempts += member_attempts
        if member_units is None:
            unknown_prices += member_attempts
        else:
            reserved_units += member_units
        output.append(
            ExperimentReportMember(
                spec,
                member.run_id,
                member.result_snapshot_id,
                "authored_fixture" if frozen.manifest.mode == "fixture" else "live",
                frozen.manifest.provider_profile_id,
                frozen.manifest.adapter,
                sanitizer.text(frozen.manifest.requested_model),
                dict(answering_models),
                unknown_models,
                frozen.manifest.provider_config_hash,
                summary.selected_count,
                dict(summary.status_counts),
                len(applicable),
                summary.selected_count - len(applicable),
                applicable_provenance,
                excluded_provenance,
                dict(summary.exclusion_counts),
                Rate.counts(correct, len(applicable), "no_applicable_expectations").source(),
                Rate.counts(correct, valid, "no_valid_applicable_answers").source(),
                0 if reuse else member_attempts,
                "0" if reuse else amount_text(member_units) if member_units is not None else None,
                member_attempts,
                amount_text(member_units) if member_units is not None else None,
                metrics["usage"],
                metrics["latency"],
            )
        )
    return ExperimentReport(
        experiment_id,
        group_id,
        selected.id,
        reuse is not None,
        0 if reuse else attempts,
        "0" if reuse else amount_text(reserved_units),
        0 if reuse else unknown_prices,
        None,
        tuple(output),
        ()
        if reuse
        else diagnostic_reports(budget.group, specs, tuple(frozen_members), tuple(planned_members)),
    )


def diagnostic_reports(
    group: object,
    specs: tuple[ExperimentMember, ...],
    frozen_members: tuple[FrozenEvaluation, ...],
    planned_members: tuple[int, ...],
) -> tuple[ExperimentDiagnosticReport, ...]:
    from deykit.contracts.execution_groups import ExecutionGroup

    assert isinstance(group, ExecutionGroup)
    request = experiment_request(group)
    reports = []
    for diagnostic in request.diagnostics:
        indexes = tuple(
            index for index, spec in enumerate(specs) if spec.diagnostic == diagnostic.name
        )
        selected = tuple(frozen_members[index] for index in indexes)
        planned = sum(planned_members[index] for index in indexes)
        valid_answers = sum(
            result.status == "valid" for frozen in selected for result in frozen.results.results
        )
        if isinstance(diagnostic, ExperimentOrder):
            summary = summarize_orders(
                selected[0].revision.definition,
                selected[0].manifest.case_ids,
                tuple(frozen.results.results for frozen in selected),
            )
            reports.append(
                ExperimentDiagnosticReport(
                    diagnostic.name,
                    diagnostic.kind,
                    summary.independent_case_count,
                    planned,
                    valid_answers,
                    summary.fully_observed_case_count,
                    summary.independent_case_count - summary.disagreement.denominator,
                    summary.disagreement.source(),
                )
            )
            continue
        baseline = frozen_members[diagnostic_base_index(request, diagnostic.name)]
        by_case = {result.case_id: result for result in baseline.results.results}
        repeats = tuple(
            {result.case_id: result for result in frozen.results.results} for frozen in selected
        )
        comparable = disagreement = fully_observed = 0
        for case_id in diagnostic.case_ids:
            base = by_case[case_id]
            observations = tuple(member[case_id] for member in repeats)
            if any(item.input_hash != base.input_hash for item in observations):
                fail("diagnostic_input_identity_mismatch", "incompatible_data")
            available = tuple(item.answer for item in observations if item.answer is not None)
            if base.answer is not None and available:
                comparable += 1
                disagreement += any(item.option_id != base.answer.option_id for item in available)
            fully_observed += base.answer is not None and len(available) == len(observations)
        reports.append(
            ExperimentDiagnosticReport(
                diagnostic.name,
                diagnostic.kind,
                len(diagnostic.case_ids),
                planned,
                valid_answers,
                fully_observed,
                len(diagnostic.case_ids) - comparable,
                Rate.counts(disagreement, comparable, "no_comparable_cases").source(),
            )
        )
    return tuple(reports)
