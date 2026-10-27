"""Admit explicit reuse of a complete experiment and its frozen evidence."""

import json

from pydantic import ValidationError

from deykit.application.dataset_support import fail
from deykit.application.evaluations import frozen_evaluation_from_records
from deykit.contracts.execution_groups import ExperimentReuse, ExperimentSnapshot
from deykit.contracts.experiments import ExperimentRequest
from deykit.contracts.json_value import (
    GROUP_SELECTION_HASH_LIMITS,
    GROUP_SELECTION_LIMITS,
    parse_json,
    semantic_hash,
)
from deykit.contracts.ports import StoredRecord
from deykit.runner.experiment_plan import ExperimentMember
from deykit.runner.group_evidence import (
    _selection_integers,
    admit_group_snapshots,
    content_hash,
    experiment_members,
    experiment_request,
    group_budget,
)
from deykit.runner.group_models import GroupPlan
from deykit.runner.group_selection import decode_group_start_selection
from deykit.runner.history import history_from_records


def reuse_intent(selection_source: str, expected_review_context_hash: str | None) -> str:
    selection = parse_json(selection_source, GROUP_SELECTION_LIMITS)
    return semantic_hash(
        {
            "command": "experiment.reuse",
            "selection": selection,
            "expected_review_context_hash": expected_review_context_hash,
        },
        limits=GROUP_SELECTION_HASH_LIMITS,
    )


def match_reuse(
    records: tuple[StoredRecord, ...], source_group_id: str, plan: GroupPlan
) -> ExperimentSnapshot:
    budget = group_budget(records, source_group_id)
    if budget.group.kind != "experiment" or experiment_request(budget.group).diagnostics:
        fail("experiment_reuse_requires_main_only", "preflight_failed")
    snapshots = admit_group_snapshots(records, source_group_id)
    if not snapshots or not isinstance(snapshots[-1], ExperimentSnapshot):
        fail("experiment_reuse_incomplete", "preflight_failed")
    snapshot = snapshots[-1]
    if len(snapshot.results) != len(plan.plans):
        fail("experiment_reuse_identity_mismatch", "preflight_failed")
    specs = experiment_members(budget.group, records)
    for desired, member, spec in zip(plan.plans, snapshot.results, specs, strict=True):
        history = history_from_records(records, member.run_id, verify_group=False)
        frozen = frozen_evaluation_from_records(
            records, member.run_id, member.result_snapshot_id, None, "original", history=history
        )
        if history.state != "completed" or any(r.status != "valid" for r in frozen.results.results):
            fail("experiment_reuse_incomplete", "preflight_failed")
        if (
            frozen.revision.definition != desired.definition
            or spec.decision.decision_id != desired.selection.decision_id
            or spec.decision.revision_id != desired.selection.revision_id
            or frozen.manifest.dataset_id != desired.selection.dataset_id
            or spec.cohort.split != desired.selection.split
            or spec.cohort.case_ids != desired.selection.case_ids
            or spec.variant.provider_id != desired.selection.provider_id
            or spec.variant.fixture_set_id != desired.selection.fixture_set_id
            or frozen.dataset.cases != desired.cases
            or frozen.labels.labels != desired.labels
            or frozen.baseline_dataset.cases != desired.development_cases
            or frozen.baseline_labels.labels != desired.development_labels
            or frozen.manifest.provider != desired.provider
            or frozen.manifest.mode != desired.selection.mode
            or frozen.manifest.fixture_set_id != desired.selection.fixture_set_id
            or frozen.manifest.option_order != desired.selection.option_order
            or tuple((c.case_id, c.input_hash, c.request, c.error) for c in history.prepared)
            != tuple((c.case_id, c.input_hash, c.request, c.error) for c in desired.prepared)
        ):
            fail("experiment_reuse_identity_mismatch", "preflight_failed")
    return snapshot


def reuse_request(reuse: ExperimentReuse) -> ExperimentRequest:
    selection = decode_group_start_selection(reuse.selection_source, expected_kind="experiment")
    assert isinstance(selection.original_selection, dict)
    try:
        request = ExperimentRequest.model_validate_json(
            json.dumps(_selection_integers(selection.original_selection["request"]))
        )
    except (ValidationError, ValueError):
        fail("invalid_experiment_selection", "incompatible_data")
    return request


def reuse_members(reuse: ExperimentReuse) -> tuple[ExperimentMember, ...]:
    return tuple(
        ExperimentMember(decision, cohort, variant, "main")
        for decision, cohort, variant in reuse_request(reuse).combinations()
    )


def admit_reuse(records: tuple[StoredRecord, ...], reuse: ExperimentReuse) -> ExperimentSnapshot:
    if reuse.content_hash != content_hash(reuse):
        fail("experiment_reuse_hash_mismatch", "incompatible_data")
    request = reuse_request(reuse)
    if (
        request.reuse_group_id != reuse.source_group_id
        or request.diagnostics
        or reuse.intent_hash
        != reuse_intent(reuse.selection_source, reuse.expected_review_context_hash)
        or (
            reuse.expected_review_context_hash is not None
            and reuse.expected_review_context_hash != reuse.review_context_hash
        )
    ):
        fail("experiment_reuse_context_mismatch", "incompatible_data")
    budget = group_budget(records, reuse.source_group_id)
    if budget.group.kind != "experiment" or experiment_request(budget.group).diagnostics:
        fail("experiment_reuse_context_mismatch", "incompatible_data")
    original = experiment_request(budget.group)
    requested_members = request.combinations()
    original_members = original.combinations()
    if (
        request.mode != original.mode
        or len(requested_members) != len(original_members)
        or any(
            desired_decision != source_decision
            or desired_cohort != source_cohort
            or (desired_variant.provider_id, desired_variant.fixture_set_id)
            != (source_variant.provider_id, source_variant.fixture_set_id)
            for (desired_decision, desired_cohort, desired_variant), (
                source_decision,
                source_cohort,
                source_variant,
            ) in zip(requested_members, original_members, strict=True)
        )
    ):
        fail("experiment_reuse_context_mismatch", "incompatible_data")
    snapshots = admit_group_snapshots(records, reuse.source_group_id)
    selected = next(
        (snapshot for snapshot in snapshots if snapshot.id == reuse.source_snapshot_id), None
    )
    if not isinstance(selected, ExperimentSnapshot) or selected.results != reuse.results:
        fail("experiment_reuse_snapshot_mismatch", "incompatible_data")
    for member in selected.results:
        history = history_from_records(records, member.run_id, verify_group=False)
        frozen = frozen_evaluation_from_records(
            records, member.run_id, member.result_snapshot_id, None, "original", history=history
        )
        if any(item.status != "valid" for item in frozen.results.results):
            fail("experiment_reuse_incomplete", "incompatible_data")
    return selected
