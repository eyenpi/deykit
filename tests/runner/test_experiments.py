"""Experiments keep their lifetime limits across members and recovery."""

import asyncio
import itertools
import threading
import time
from contextlib import contextmanager

import pytest

from deykit.application.experiments import (
    ExperimentCohort,
    ExperimentDecision,
    ExperimentRequest,
    ExperimentService,
    ExperimentVariant,
)
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.experiments import ExperimentOrder, ExperimentRepeat
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    DecisionDraft,
    DecisionRevision,
    DispatchOutcome,
    ExecutionSettings,
)
from deykit.domain.definitions import definition_hash


def experiment(source, *, budget="0.30"):
    draft = load_record(DecisionDraft, source.read(ResourceKey("drafts", "decision")).body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    revision = DecisionRevision(
        id="revision",
        decision_id="decision",
        definition=definition,
        content_hash=definition_hash(definition),
        created_at="2026-10-05T00:00:00Z",
    )
    source.commit(
        "revision-operation",
        (
            SourceChange(
                ResourceKey("revisions", revision.id, ("decision",)), dump_record(revision), None
            ),
        ),
    )
    return ExperimentRequest(
        decisions=(
            ExperimentDecision(decision_id="decision", revision_id="revision", modality="text"),
        ),
        cohorts=(ExperimentCohort(dataset_id="data"),),
        variants=(
            ExperimentVariant(name="first", fixture_set_id="set", reservation_usd="0.10"),
            ExperimentVariant(name="second", fixture_set_id="set", reservation_usd="0.10"),
        ),
        mode="fixture",
        settings=ExecutionSettings(max_attempts=4, concurrency=2),
        budget_usd=budget,
    )


def test_preview_and_shared_budget_survive_replay_and_resume(setup):
    source, runner, factory, _ = setup(count=2)
    request = experiment(source)
    service = ExperimentService(runner)
    before = source.capture_snapshot()
    preview = service.preview(request)
    assert preview.initial_requests == 4
    assert preview.initial_reservation_usd == "0.40"
    assert len(preview.members) == 2
    assert source.capture_snapshot() == before and not factory.calls

    result = asyncio.run(service.start(request, operation_id="experiment"))
    assert len(factory.calls) == 3
    assert result.attempts_used == 3
    assert result.reserved_usd == "0.30"
    assert result.remaining_usd == "0"
    assert all(member.group_attempts_remaining == 1 for member in result.members)
    assert all(member.attempts_remaining == 0 for member in result.members)
    assert [case.status for case in result.members[1].cases].count("pending") == 1
    assert any(
        member.reason and member.reason.reason == "experiment_reservation_budget"
        for member in result.members
    )

    replay = asyncio.run(service.start(request, operation_id="experiment"))
    assert replay.group_id == result.group_id and replay.replayed
    resumed = asyncio.run(service.resume(result.group_id, operation_id="resume"))
    assert resumed.reserved_usd == "0.30"
    assert len(factory.calls) == 3


def test_group_staging_validates_the_full_group_once_per_stage(setup, monkeypatch):
    from deykit.runner import group_evidence, group_repository
    from deykit.runner.group_selection import encode_group_start_selection, group_start_intent

    source, runner, _, _ = setup(count=1)
    request = experiment(source).model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(
                    name=f"variant-{index}", fixture_set_id="set", reservation_usd="0"
                )
                for index in range(8)
            ),
            "settings": ExecutionSettings(max_attempts=8, concurrency=2),
        }
    )
    service = ExperimentService(runner)
    plan = service._plan(request)
    selection = encode_group_start_selection(service._selection_source(request))
    group, frozen = service.groups.store.stage_freeze(
        plan, "operation", group_start_intent(selection), selection.stored_source
    )
    count = 0
    original = group_evidence.group_budget

    def count_validation(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(group_evidence, "group_budget", count_validation)
    monkeypatch.setattr(group_repository, "group_budget", count_validation)
    segment, changes = service.groups.store.stage_segment(
        group, "operation", 1, False, service.groups._staged(frozen), initial=True
    )
    assert count == 1
    ready = service.groups.store.stage_ready(segment, service.groups._staged((*frozen, *changes)))
    assert count == 2 and len(ready) == 8


def test_group_snapshot_admission_reuses_member_histories(setup, monkeypatch):
    from deykit.runner import group_evidence
    from deykit.runner import history as history_module

    source, runner, _, _ = setup(count=1)
    request = experiment(source, budget="0.40").model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(
                    name=f"variant-{index}", fixture_set_id="set", reservation_usd="0.10"
                )
                for index in range(4)
            ),
            "settings": ExecutionSettings(max_attempts=4, concurrency=2),
        }
    )
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="four-members"))
    records = source.capture_snapshot()
    count = 0
    original = group_evidence.group_budget

    def count_validation(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(group_evidence, "group_budget", count_validation)
    monkeypatch.setattr(history_module, "group_budget", count_validation)
    snapshots = group_evidence.admit_group_snapshots(records, result.group_id)
    assert snapshots and len(snapshots[-1].results) == 4
    assert count == 1


def test_explicit_members_select_only_compatible_arms_under_one_budget(setup):
    import json

    from deykit.application.experiment_reports import experiment_report

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.30")
    original = load_record(
        DecisionRevision, source.read(ResourceKey("revisions", "revision", ("decision",))).body
    )
    second = original.model_copy(update={"id": "revision-2"})
    source.commit(
        "second-revision",
        (
            SourceChange(
                ResourceKey("revisions", "revision-2", ("decision",)), dump_record(second), None
            ),
        ),
    )
    data = request.model_dump(mode="json")
    data["decisions"].append(
        {"decision_id": "decision", "revision_id": "revision-2", "modality": "text"}
    )
    data["include"] = [
        {"decision_index": 0, "cohort_index": 0, "variant": "first"},
        {"decision_index": 1, "cohort_index": 0, "variant": "second"},
    ]
    data["diagnostics"] = [
        {
            "kind": "repeat",
            "name": "repeat",
            "decision_index": 1,
            "cohort_index": 0,
            "variant": "second",
            "case_ids": ["case-00"],
            "count": 1,
        }
    ]
    data["settings"]["max_attempts"] = 3
    selected = ExperimentRequest.model_validate_json(json.dumps(data))
    service = ExperimentService(runner)
    preview = service.preview(selected)
    assert preview.initial_requests == 3 and len(preview.member_details) == 3
    assert [(item.decision.revision_id, item.variant.name) for item in preview.member_details] == [
        ("revision", "first"),
        ("revision-2", "second"),
        ("revision-2", "second"),
    ]
    result = asyncio.run(service.start(selected, operation_id="selected"))
    assert result.attempts_used == 3 and len(factory.calls) == 3
    report = experiment_report(source.capture_snapshot(), result.group_id)
    assert len(report.members) == 3 and report.diagnostics[0].independent_cases == 1


def test_explicit_members_allow_jev_text_and_openai_webp_image(setup, tmp_path):
    from PIL import Image
    from test_image_execution import seed_image

    from deykit.contracts.experiments import ExperimentSelection
    from deykit.contracts.images import CaseImage, ImagePreparation
    from deykit.contracts.records import ProviderProfile
    from deykit.images.local import LocalImages
    from deykit.providers.choice import JEV_DESTINATION, JevChoiceCompiler
    from deykit.providers.openai_choice import DESTINATION, MODEL, OpenAIChoiceCompiler

    source, runner, factory, _, root, definition = seed_image(setup, tmp_path, select=False)
    Image.new("RGB", (280, 280), "red").save(root / "product.webp")
    asset = LocalImages(root).prepare("product.webp", ImagePreparation())
    key = ResourceKey("cases", "product", ("data",))
    stored = source.read(key)
    case = load_record(CaseRecord, stored.body)
    case = case.model_copy(
        update={
            "images": (
                CaseImage(name="product", asset_id=asset.id, source_hash=asset.source.content_hash),
            )
        }
    )
    source.commit(
        "webp",
        (
            SourceChange(ResourceKey("image_assets", asset.id), dump_record(asset), None),
            SourceChange(key, dump_record(case), stored.etag),
        ),
    )
    image_definition = definition.model_copy(update={"selected_images": ("product",)})
    revisions = []
    for name, value in (("text", definition), ("image", image_definition)):
        revision = DecisionRevision(
            id=name,
            decision_id="decision",
            definition=value,
            content_hash=definition_hash(value),
            created_at="2026-10-05T00:00:00Z",
        )
        revisions.append(
            SourceChange(ResourceKey("revisions", name, ("decision",)), dump_record(revision), None)
        )
    profiles = {
        "jev": ProviderProfile(
            id="jev",
            adapter="jev",
            requested_model="jev-1.13.0",
            destination=JEV_DESTINATION,
            credential_ref="env:UNUSED_TEST_KEY",
        ),
        "openai": ProviderProfile(
            id="openai",
            adapter="openai",
            requested_model=MODEL,
            destination=DESTINATION,
            credential_ref="env:UNUSED_TEST_KEY",
        ),
    }
    source.commit(
        "profiles-and-revisions",
        tuple(revisions)
        + tuple(
            SourceChange(ResourceKey("providers", name), dump_record(profile), None)
            for name, profile in profiles.items()
        ),
    )

    class Backend:
        def __init__(self, profile):
            self.compiler = (
                OpenAIChoiceCompiler() if profile.adapter == "openai" else JevChoiceCompiler()
            )

        def preflight(self, *_args):
            return None

        def for_case(self, case_id):
            return factory.for_case(case_id)

    factory.profile = lambda provider_id, _fixture: profiles[provider_id]
    factory.resolve = lambda profile, _fixture: Backend(profile)
    request = ExperimentRequest(
        mode="live",
        decisions=(
            ExperimentDecision(decision_id="decision", revision_id="text", modality="text"),
            ExperimentDecision(decision_id="decision", revision_id="image", modality="image"),
        ),
        cohorts=(ExperimentCohort(dataset_id="data"),),
        variants=(
            ExperimentVariant(name="jev", provider_id="jev", reservation_usd="0.10"),
            ExperimentVariant(name="openai", provider_id="openai", reservation_usd="0.10"),
        ),
        include=(
            ExperimentSelection(decision_index=0, cohort_index=0, variant="jev"),
            ExperimentSelection(decision_index=1, cohort_index=0, variant="openai"),
        ),
        settings=ExecutionSettings(max_attempts=2, concurrency=2),
        budget_usd="0.20",
    )
    service = ExperimentService(runner)
    preview = service.preview(request)
    assert preview.group is not None and preview.initial_requests == 2
    assert not preview.compatibility_failures
    result = asyncio.run(service.start(request, operation_id="compatible"))
    assert result.attempts_used == 2
    assert {call[1].adapter for call in factory.calls} == {"jev", "openai"}


def test_unused_variant_with_unknown_price_does_not_block_selected_work(setup):
    from deykit.contracts.experiments import ExperimentSelection

    source, runner, factory, _ = setup(count=1)
    base = experiment(source, budget="0.10")
    request = ExperimentRequest.model_validate(
        base.model_copy(
            update={
                "include": (
                    ExperimentSelection(decision_index=0, cohort_index=0, variant="first"),
                ),
                "variants": (
                    base.variants[0],
                    base.variants[1].model_copy(update={"reservation_usd": None}),
                ),
            }
        )
    )
    service = ExperimentService(runner)
    preview = service.preview(request)
    assert not preview.compatibility_failures and preview.initial_requests == 1
    result = asyncio.run(
        service.start(
            request,
            operation_id="selected",
            expected_review_context_hash=preview.group.review_context_hash,
        )
    )
    assert result.attempts_used == 1 and len(factory.calls) == 1


def test_reuse_ignores_unselected_variants_and_cohorts(setup):
    from deykit.contracts.experiments import ExperimentSelection

    source, runner, factory, _ = setup(count=1)
    base = experiment(source, budget="0.10")
    original = ExperimentRequest.model_validate(
        base.model_copy(
            update={
                "include": (
                    ExperimentSelection(decision_index=0, cohort_index=0, variant="first"),
                ),
            }
        )
    )
    service = ExperimentService(runner)
    result = asyncio.run(service.start(original, operation_id="original"))
    reused = original.model_copy(
        update={
            "reuse_group_id": result.group_id,
            "cohorts": (*original.cohorts, ExperimentCohort(dataset_id="unused")),
            "variants": (
                original.variants[0],
                original.variants[1].model_copy(update={"fixture_set_id": "unused"}),
            ),
        }
    )
    preview = service.preview(reused)
    assert not preview.compatibility_failures and preview.reused_requests == 1
    reuse = asyncio.run(service.start(reused, operation_id="reuse"))
    assert reuse.reuse_id and service.read(reuse.reuse_id).reused_group_id == result.group_id
    assert len(factory.calls) == 1


def test_live_reuse_needs_no_available_credential(setup):
    from deykit.application.errors import ServiceFailure
    from deykit.contracts.records import ProviderProfile
    from deykit.providers.choice import JEV_DESTINATION

    source, runner, factory, _ = setup(count=1)
    factory.profile_value = ProviderProfile(
        id="live",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref="env:UNUSED_TEST_KEY",
    )
    source.commit(
        "provider-config",
        (SourceChange(ResourceKey("providers", "live"), dump_record(factory.profile_value), None),),
    )
    request = experiment(source, budget="0.10").model_copy(
        update={
            "mode": "live",
            "variants": (
                ExperimentVariant(name="live", provider_id="live", reservation_usd="0.10"),
            ),
        }
    )
    service = ExperimentService(runner)
    original = asyncio.run(service.start(request, operation_id="original-live"))
    factory.error = ServiceError(code="preflight_failed", reason="credential_unavailable")
    reuse = request.model_copy(update={"reuse_group_id": original.group_id})
    preview = service.preview(reuse)
    assert not preview.compatibility_failures and preview.reused_requests == 1
    receipt = asyncio.run(service.start(reuse, operation_id="reuse-live"))
    assert receipt.reuse_id and len(factory.calls) == 1
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(service.start(request, operation_id="new-live"))
    assert failure.value.error.reason == "credential_unavailable"


def test_resume_preview_distinguishes_eligible_cases_from_remaining_budget(setup):
    source, runner, factory, _ = setup(count=2)
    request = experiment(source, budget="0.10")
    service = ExperimentService(runner)
    result = asyncio.run(service.start(request, operation_id="start"))
    preview = service.preview_resume(result.group_id)
    assert preview.group.attempts_remaining == 3
    assert preview.remaining_usd == "0"
    assert sum(len(member.eligible_case_ids) for member in preview.members) == 3
    assert all(member.maximum_dispatchable_attempts == 0 for member in preview.members)
    assert len(factory.calls) == 1


def test_resume_preview_includes_possible_rate_retries(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.30").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            ),
            "settings": ExecutionSettings(max_attempts=3, concurrency=1, max_retries_per_case=1),
        }
    )
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
        ),
        DispatchOutcome(
            state="known",
            retryable=True,
            error=ServiceError(code="provider_rejected", reason="rate_limit"),
        ),
    ]
    service = ExperimentService(runner)
    started = asyncio.run(service.start(request, operation_id="start"))
    preview = service.preview_resume(started.group_id, retry_unknown=True)
    assert preview.members[0].eligible_case_ids == ("case-00",)
    assert preview.members[0].maximum_dispatchable_attempts == 2
    result = asyncio.run(
        service.resume(started.group_id, operation_id="resume", retry_unknown=True)
    )
    assert result.attempts_used == 3 and len(factory.calls) == 3


def test_experiment_member_can_exceed_ordinary_run_plan_limit(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure
    from deykit.runner import planner

    source, runner, _, _ = setup(count=2)
    request = experiment(source, budget="0.40")
    monkeypatch.setattr(planner, "MAX_PLAN_BYTES", 1_000)
    service = ExperimentService(runner)
    preview = service.preview(request)
    assert preview.group is not None and preview.initial_requests == 4
    _, selections, _ = service._inputs(request)
    with pytest.raises(ServiceFailure) as failure:
        runner.preview(selections[0])
    assert failure.value.error.reason == "run_resource_limit"


def test_experiment_preview_stops_at_the_aggregate_plan_limit(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=2)
    request = experiment(source).model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(name=f"v-{index}", fixture_set_id="set", reservation_usd="0")
                for index in range(8)
            )
        }
    )
    service = ExperimentService(runner)
    first = service._plan(request).plans[0]
    one_size = sum(
        len(item.body) for item in first.review_records if item.key.collection != "image_assets"
    ) + sum(len(dump_record(item.request)) for item in first.prepared if item.request is not None)
    monkeypatch.setattr(experiments, "MAX_EXPERIMENT_PLAN_BYTES", one_size * 5 // 2)
    original = factory.compiler.compile
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(factory.compiler, "compile", counted)
    before = source.capture_snapshot()
    preview = service.preview(request)
    assert preview.group is None
    assert preview.compatibility_failures[0].error.reason == "execution_group_resource_limit"
    assert preview.unplanned_members == 8
    assert calls <= 6
    assert source.capture_snapshot() == before and not factory.calls


def test_experiment_review_does_not_repeat_full_member_payloads(setup, monkeypatch):
    from deykit.contracts.json_value import JsonLimits, canonical_bytes
    from deykit.runner import review

    source, runner, _, _ = setup(count=2)
    request = experiment(source).model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(name=f"v-{index}", fixture_set_id="set", reservation_usd="0")
                for index in range(8)
            )
        }
    )
    service = ExperimentService(runner)
    plan = service._plan(request)
    per_member = len(canonical_bytes(review.run_review_payload(plan.plans[0])))
    monkeypatch.setattr(
        review,
        "_REVIEW_LIMITS",
        JsonLimits(max_bytes=per_member * 2, max_depth=128, max_nodes=2_000_000),
    )
    preview = service.preview(request)
    assert preview.group is not None and preview.initial_requests == 16


def test_large_experiment_selection_can_be_encoded_and_frozen():
    import json

    from deykit.contracts.execution_groups import ExecutionGroup, ExecutionMember
    from deykit.runner.group_selection import (
        decode_group_start_selection,
        encode_group_start_selection,
    )

    source = json.dumps({"kind": "experiment", "request": {"scope": "x" * 1_100_000}})
    encoded = encode_group_start_selection(source, expected_review_context_hash="a" * 64)
    decoded = decode_group_start_selection(encoded.stored_source, expected_kind="experiment")
    assert decoded.original_selection == encoded.original_selection
    group = ExecutionGroup(
        id="group",
        kind="experiment",
        members=(
            ExecutionMember(
                run_id="run", manifest_hash="a" * 64, prepared_hash="b" * 64, initial_requests=1
            ),
        ),
        max_attempts=1,
        deadline_seconds=1,
        operation_id="operation",
        intent_hash="c" * 64,
        selection_source=encoded.stored_source,
        content_hash="d" * 64,
        created_at="2026-10-05T00:00:00Z",
    )
    assert group.selection_source == encoded.stored_source


def test_frozen_dataset_admits_large_explicit_case_scope():
    from deykit.application.splits import admit_dataset_snapshot
    from deykit.contracts.evidence import evidence_hash
    from deykit.contracts.json_value import GROUP_SELECTION_LIMITS, dump_json
    from deykit.contracts.records import DatasetSnapshot

    case_ids = [f"c{index:05}-" + "x" * 120 for index in range(8_200)]
    selection = dump_json({"split": "all", "case_ids": case_ids}, limits=GROUP_SELECTION_LIMITS)
    assert len(selection) > 1_048_576
    snapshot = DatasetSnapshot(
        id="snapshot",
        dataset_id="data",
        cases=(),
        content_hash=evidence_hash(()),
        created_at="2026-10-05T00:00:00Z",
        selection_source=selection,
    )
    assert admit_dataset_snapshot(snapshot) == snapshot


def test_large_valid_experiment_request_reaches_scope_preflight(setup):
    source, runner, factory, _ = setup(count=1)
    base = experiment(source)
    case_ids = tuple(f"missing-{index}" for index in range(10_000))
    request = base.model_copy(
        update={
            "cohorts": tuple(
                ExperimentCohort(dataset_id="data", case_ids=case_ids) for _ in range(11)
            ),
            "variants": (base.variants[0],),
        }
    )
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None
    assert all(
        failure.error.reason == "selected_case_missing"
        for failure in preview.compatibility_failures
    )
    assert not factory.calls


def test_experiment_freeze_stops_before_staging_the_whole_oversized_group(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure
    from deykit.runner import group_repository
    from deykit.runner.group_selection import decode_group_start_selection, group_start_intent

    source, runner, _, _ = setup(count=2)
    request = experiment(source).model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(name=f"v-{index}", fixture_set_id="set", reservation_usd="0")
                for index in range(8)
            )
        }
    )
    service = ExperimentService(runner)
    plan = service._plan(request)
    original = runner.repository.stage_freeze
    sample = original(plan.plans[0], "sample", run_id="sample", group_id="group")
    one_size = sum(len(item.body or b"") for item in sample)
    monkeypatch.setattr(group_repository, "MAX_EXPERIMENT_PLAN_BYTES", one_size * 5 // 2)
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.repository, "stage_freeze", counted)
    selection = service._selection_source(request)
    digest = group_start_intent(decode_group_start_selection(selection, expected_kind="experiment"))
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        service.groups.store.stage_freeze(plan, "start", digest, selection)
    assert failure.value.error.reason == "execution_group_resource_limit"
    assert calls <= 3
    assert source.capture_snapshot() == before


def test_incompatible_preview_also_obeys_the_aggregate_plan_limit(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=2)
    request = experiment(source).model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(name=f"v-{index}", fixture_set_id="set", reservation_usd="0")
                for index in range(8)
            )
        }
    )
    service = ExperimentService(runner)
    first = service._plan(request).plans[0]
    one_size = sum(
        len(item.body) for item in first.review_records if item.key.collection != "image_assets"
    ) + sum(len(dump_record(item.request)) for item in first.prepared if item.request is not None)
    monkeypatch.setattr(experiments, "MAX_EXPERIMENT_PLAN_BYTES", one_size * 5 // 2)
    original = factory.compiler.compile
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(factory.compiler, "compile", counted)
    request = request.model_copy(
        update={
            "decisions": (
                ExperimentDecision(decision_id="decision", revision_id="missing", modality="text"),
                request.decisions[0],
            )
        }
    )
    preview = service.preview(request)
    assert preview.group is None and preview.unplanned_members == 14
    assert any(
        failure.error.reason == "execution_group_resource_limit"
        for failure in preview.compatibility_failures
    )
    assert calls <= 6 and not factory.calls


def test_preview_reports_missing_revision_without_losing_valid_members(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source).model_copy(
        update={
            "decisions": (
                ExperimentDecision(decision_id="decision", revision_id="missing", modality="text"),
                ExperimentDecision(decision_id="decision", revision_id="revision", modality="text"),
            ),
        }
    )
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None
    assert preview.unplanned_members == 2
    assert preview.initial_requests == 2
    assert [failure.member_index for failure in preview.compatibility_failures] == [0, 1]
    assert all(
        failure.error.reason == "experiment_revision_missing"
        for failure in preview.compatibility_failures
    )
    assert not factory.calls


def test_incompatible_reuse_preview_does_not_claim_fresh_work(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source).model_copy(
        update={
            "decisions": (
                ExperimentDecision(decision_id="decision", revision_id="missing", modality="text"),
                ExperimentDecision(decision_id="decision", revision_id="revision", modality="text"),
            ),
            "reuse_group_id": "source-group",
        }
    )
    preview = ExperimentService(runner).preview(request)
    assert preview.compatibility_failures and preview.unplanned_members == 2
    assert preview.fresh_requests == preview.reused_requests == 0
    assert preview.known_reservation_usd == "0" and preview.unknown_price_requests == 0
    assert not factory.calls


def test_expanded_case_selection_limit_rejects_before_planning(setup, monkeypatch):
    from deykit.application import experiments
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=2)
    request = experiment(source).model_copy(
        update={"cohorts": (ExperimentCohort(dataset_id="data", case_ids=("case-00", "case-01")),)}
    )
    monkeypatch.setattr(experiments, "MAX_EXPANDED_CASE_IDS", 3)
    before = source.capture_snapshot()
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None and preview.unplanned_members == 2
    assert preview.compatibility_failures[0].error.reason == "experiment_expanded_selection_limit"
    assert not preview.member_previews and not factory.calls
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(ExperimentService(runner).start(request, operation_id="too-large"))
    assert failure.value.error.reason == "experiment_expanded_selection_limit"
    assert source.capture_snapshot() == before and not factory.calls


def test_expanded_limits_count_actual_distinct_choice_orders(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.30").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="first", fixture_set_id="set", reservation_usd="0.10"),
            ),
            "diagnostics": (
                ExperimentOrder(
                    name="orders",
                    decision_index=0,
                    cohort_index=0,
                    variant="first",
                    case_ids=("case-00",),
                    orders=4,
                ),
            ),
            "settings": ExecutionSettings(max_attempts=3, concurrency=1),
        }
    )
    monkeypatch.setattr(experiments, "MAX_EXPANDED_CASE_IDS", 2)
    preview = ExperimentService(runner).preview(request)
    assert preview.group is not None and len(preview.member_details) == 3
    assert preview.initial_requests == 3 and not factory.calls


def test_member_limit_rejects_before_planning(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=1)
    request = experiment(source).model_copy(
        update={
            "variants": tuple(
                ExperimentVariant(name=f"v-{i}", fixture_set_id="set") for i in range(4)
            )
        }
    )
    monkeypatch.setattr(experiments, "MAX_EXPERIMENT_MEMBERS", 3)
    before = source.capture_snapshot()
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None and preview.unplanned_members == 4
    assert preview.compatibility_failures[0].error.reason == "experiment_member_limit"
    assert source.capture_snapshot() == before and not factory.calls


@pytest.mark.parametrize("missing_revision", (False, True))
def test_large_expansion_never_falls_back_to_per_decision_planning(
    setup, monkeypatch, missing_revision
):
    source, runner, factory, _ = setup(count=1)
    base = experiment(source)
    decisions = tuple(
        ExperimentDecision(
            decision_id="decision",
            revision_id="missing" if missing_revision and index == 0 else "revision",
            modality="text",
        )
        for index in range(100)
    )
    variants = tuple(
        ExperimentVariant(name=f"v-{index}", fixture_set_id="set") for index in range(100)
    )
    request = base.model_copy(
        update={
            "decisions": decisions,
            "variants": variants,
            "diagnostics": (
                ExperimentRepeat(
                    name="repeat",
                    decision_index=0,
                    cohort_index=0,
                    variant="v-0",
                    case_ids=("case-00",),
                ),
            ),
        }
    )

    def no_planning(*args, **kwargs):
        raise AssertionError("oversized expansion must not be planned")

    monkeypatch.setattr(runner.planner, "prepare_many", no_planning)
    before = source.capture_snapshot()
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None and preview.unplanned_members is None
    assert preview.compatibility_failures[0].error.reason == "experiment_member_limit"
    assert source.capture_snapshot() == before and not factory.calls


def test_missing_revision_does_not_bypass_diagnostic_member_limit(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=1)
    base = experiment(source)
    request = base.model_copy(
        update={
            "decisions": (
                ExperimentDecision(decision_id="decision", revision_id="missing", modality="text"),
                base.decisions[0],
            ),
            "variants": (base.variants[0],),
            "diagnostics": (
                ExperimentRepeat(
                    name="repeat",
                    decision_index=1,
                    cohort_index=0,
                    variant="first",
                    case_ids=("case-00",),
                    count=2,
                ),
            ),
        }
    )
    monkeypatch.setattr(experiments, "MAX_EXPERIMENT_MEMBERS", 3)

    def no_planning(*args, **kwargs):
        raise AssertionError("uncertain oversized expansion must not be planned")

    monkeypatch.setattr(runner.planner, "prepare_many", no_planning)
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None and preview.unplanned_members is None
    assert preview.compatibility_failures[0].error.reason == "experiment_revision_missing"
    assert not factory.calls


def test_missing_revision_does_not_bypass_global_case_reference_limit(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=2)
    base = experiment(source)
    request = base.model_copy(
        update={
            "decisions": (
                ExperimentDecision(decision_id="decision", revision_id="missing", modality="text"),
                base.decisions[0],
            ),
            "variants": (base.variants[0],),
            "cohorts": (ExperimentCohort(dataset_id="data", case_ids=("case-00", "case-01")),),
        }
    )
    monkeypatch.setattr(experiments, "MAX_EXPANDED_CASE_IDS", 3)

    def no_planning(*args, **kwargs):
        raise AssertionError("globally oversized references must not be planned")

    monkeypatch.setattr(runner.planner, "prepare_many", no_planning)
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None and preview.unplanned_members == 2
    assert preview.compatibility_failures[0].error.reason == "experiment_expanded_selection_limit"
    assert not factory.calls


def test_compatible_actual_orders_get_individual_preflight_failures(setup, monkeypatch):
    from deykit.application import experiments

    source, runner, factory, _ = setup(count=1)
    base = experiment(source)
    request = base.model_copy(
        update={
            "variants": (base.variants[0],),
            "diagnostics": (
                ExperimentOrder(
                    name="orders",
                    decision_index=0,
                    cohort_index=0,
                    variant="first",
                    case_ids=("case-00",),
                    orders=4,
                ),
            ),
        }
    )
    monkeypatch.setattr(experiments, "MAX_EXPERIMENT_MEMBERS", 3)
    factory.error = ServiceError(code="preflight_failed", reason="credential_unavailable")
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None and len(preview.member_details) == 3
    assert preview.unplanned_members == 3
    assert all(
        failure.error.reason == "credential_unavailable"
        for failure in preview.compatibility_failures
    )


def test_live_preview_rejects_unrepresentable_dense_result_snapshots(setup, monkeypatch):
    from deykit.contracts.records import ProviderProfile
    from deykit.providers.choice import JEV_DESTINATION
    from deykit.runner import result_limits

    long_ids = tuple(f"category-{index:03}" + "x" * 100 for index in range(104))
    short_ids = tuple(f"category-{index:03}" for index in range(104))
    assert result_limits.minimum_dense_result_size(
        "case", "q", long_ids
    ) > result_limits.experiment_case_result_limit(2500, 2500)
    assert result_limits.minimum_dense_result_size(
        "case", "q", short_ids
    ) < result_limits.experiment_case_result_limit(2500, 2500)
    assert result_limits.minimum_dense_result_size(
        "case", "q", long_ids
    ) < result_limits.experiment_case_result_limit(2500, 1)

    source, runner, factory, _ = setup(count=1)
    factory.profile_value = ProviderProfile(
        id="live",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref="env:UNUSED_TEST_KEY",
    )
    source.commit(
        "provider-config",
        (SourceChange(ResourceKey("providers", "live"), dump_record(factory.profile_value), None),),
    )
    request = experiment(source, budget="0.10").model_copy(
        update={
            "mode": "live",
            "variants": (
                ExperimentVariant(name="live", provider_id="live", reservation_usd="0.10"),
            ),
        }
    )
    monkeypatch.setattr(result_limits, "MAX_EXPERIMENT_RESULT_BYTES", 200)
    before = source.capture_snapshot()
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None
    assert preview.compatibility_failures[0].error.reason == "experiment_result_snapshot_capacity"
    assert source.capture_snapshot() == before and not factory.calls


def test_result_capacity_ignores_inputs_that_cannot_dispatch(setup, monkeypatch):
    from deykit.contracts.records import ProviderProfile
    from deykit.providers.choice import JEV_DESTINATION
    from deykit.runner import result_limits

    source, runner, factory, _ = setup(count=1, invalid=(0,))
    factory.profile_value = ProviderProfile(
        id="live",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref="env:UNUSED_TEST_KEY",
    )
    source.commit(
        "provider-config",
        (SourceChange(ResourceKey("providers", "live"), dump_record(factory.profile_value), None),),
    )
    request = experiment(source, budget="0.10").model_copy(
        update={
            "mode": "live",
            "variants": (
                ExperimentVariant(name="live", provider_id="live", reservation_usd="0.10"),
            ),
        }
    )
    monkeypatch.setattr(result_limits, "MAX_EXPERIMENT_RESULT_BYTES", 200)
    preview = ExperimentService(runner).preview(request)
    assert preview.group is not None and preview.initial_requests == 0
    assert len(preview.members[0].invalid_cases) == 1 and not factory.calls


def test_oversized_answer_is_recorded_as_error_without_stranding_snapshot(setup, monkeypatch):
    from deykit.contracts.records import NormalizedAnswer
    from deykit.runner import result_limits

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.10").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            ),
        }
    )
    probabilities = '{"yes":0.' + "0" * 1999 + '1,"no":0.' + "9" * 2000 + "}"
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(
                question_id="q", option_id="no", probabilities_source=probabilities
            ),
            raw_response_source='{"retained":true}',
            usage_source='{"input_tokens":3,"output_tokens":1}',
        )
    ]
    monkeypatch.setattr(result_limits, "MAX_EXPERIMENT_RESULT_BYTES", 2048)
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="oversized-result"))
    case = result.members[0].cases[0]
    assert (
        case.status == "response_error" and case.error.reason == "experiment_result_resource_limit"
    )
    assert result.group.snapshot_id is not None and result.attempts_used == 1
    history = runner.repository.history(result.members[0].run_id)
    stored = history.attempt_events[-1].outcome
    assert stored.raw_response_source == '{"retained":true}'
    assert stored.usage_source == '{"input_tokens":3,"output_tokens":1}'


def test_low_attempt_cap_allows_a_larger_answer_and_keeps_other_cases_pending(setup, monkeypatch):
    from deykit.contracts.records import NormalizedAnswer
    from deykit.runner import result_limits

    source, runner, factory, _ = setup(count=2)
    request = experiment(source, budget="0.10").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            ),
            "settings": ExecutionSettings(max_attempts=1, concurrency=1),
        }
    )
    probabilities = '{"yes":0.' + "0" * 699 + '1,"no":0.' + "9" * 700 + "}"
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(
                question_id="q", option_id="no", probabilities_source=probabilities
            ),
        )
    ]
    monkeypatch.setattr(result_limits, "MAX_EXPERIMENT_RESULT_BYTES", 3000)
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="low-cap"))
    assert [case.status for case in result.members[0].cases] == ["valid", "pending"]
    assert result.group.snapshot_id is not None and result.attempts_used == 1


def test_oversized_error_is_bounded_before_snapshot(setup, monkeypatch):
    from deykit.runner import result_limits

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.10").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            ),
        }
    )
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown",
            error=ServiceError(code="provider_rejected", row=int("9" * 1200)),
        )
    ]
    monkeypatch.setattr(result_limits, "MAX_EXPERIMENT_RESULT_BYTES", 2048)
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="large-error"))
    case = result.members[0].cases[0]
    assert case.status == "unknown" and case.error.reason == "experiment_result_resource_limit"
    assert result.group.snapshot_id is not None and result.attempts_used == 1


def test_unknown_attempt_keeps_its_reservation(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.10")
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
        )
    ]
    service = ExperimentService(runner)
    result = asyncio.run(service.start(request, operation_id="experiment"))
    assert result.reserved_usd == "0.10"
    assert result.members[0].cases[0].status == "unknown"
    resumed = asyncio.run(service.resume(result.group_id, operation_id="retry", retry_unknown=True))
    assert resumed.reserved_usd == "0.10"
    assert len(factory.calls) == 1


def test_recovery_allows_another_snapshot_for_the_same_segment(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.20").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            )
        }
    )
    service = ExperimentService(runner)
    original_settle = runner.repository.settle
    acknowledged = []

    def fail_settlement(*args, **kwargs):
        raise ServiceFailure(ServiceError(code="internal_error", reason="persistence_failed"))

    monkeypatch.setattr(runner.repository, "settle", fail_settlement)
    with pytest.raises(ServiceFailure):
        asyncio.run(service.start(request, operation_id="start", on_created=acknowledged.append))
    assert len(factory.calls) == 1 and len(acknowledged) == 1
    monkeypatch.setattr(runner.repository, "settle", original_settle)
    group_id = acknowledged[0].group_id
    recovered = asyncio.run(service.resume(group_id, operation_id="recover"))
    assert recovered.members[0].cases[0].status == "unknown"
    assert service.read(group_id).group.snapshot_id is not None
    assert len(factory.calls) == 1


def test_experiment_is_acknowledged_before_any_provider_call(setup):
    source, runner, factory, _ = setup(count=1)
    acknowledged = []

    def created(event):
        assert not factory.calls
        acknowledged.append(event.group_id)

    result = asyncio.run(
        ExperimentService(runner).start(
            experiment(source, budget="0.20"), operation_id="acknowledge", on_created=created
        )
    )
    assert acknowledged == [result.group_id]


def test_unsent_reservation_is_not_counted_as_unknown_usage(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.20")
    cancelled = False

    def stop_before_dispatch(stage, attempt):
        nonlocal cancelled
        if stage == "after_intent" and not cancelled:
            cancelled = True
            runner.cancel(attempt.run_id, operation_id="cancel-before-send")

    runner.scheduler.hook = stop_before_dispatch
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="start"))
    assert result.attempts_used >= 1
    assert result.unknown_usage_attempts == 0
    assert not factory.calls


def test_bulk_not_sent_after_dispatch_marker_has_no_unknown_usage(setup):
    source, runner, factory, _ = setup(count=64)
    request = experiment(source, budget="1.00").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="first", fixture_set_id="set", reservation_usd="0.10"),
            ),
            "settings": ExecutionSettings(max_attempts=8, concurrency=8),
        }
    )

    async def fail_first(_case_id, _request):
        return DispatchOutcome(
            state="known",
            error=ServiceError(code="provider_auth", reason="auth_failed"),
            provider_wide=True,
        )

    factory.callback = fail_first
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="bulk-failure"))
    assert len(factory.calls) == 1
    assert result.unknown_usage_attempts == 1


def test_priority_inspection_waits_for_group_start_and_resume_acknowledgement(setup, monkeypatch):
    from deykit.storage import FileProjectSource

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.20").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            )
        }
    )
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
        )
    ]
    service = ExperimentService(runner)
    original = service.groups.store.ready
    acknowledgements = []

    async def exercise(reader):
        def ready_then_inspect(*args, **kwargs):
            result = original(*args, **kwargs)
            priority = reader.priority_read()
            priority.__enter__()

            async def release():
                await asyncio.sleep(0.1)
                priority.__exit__(None, None, None)

            asyncio.create_task(release())
            return result

        monkeypatch.setattr(service.groups.store, "ready", ready_then_inspect)
        first = await service.start(
            request, operation_id="priority-start", on_created=acknowledgements.append
        )
        return await service.resume(
            first.group_id,
            operation_id="priority-resume",
            retry_unknown=True,
            on_resumed=acknowledgements.append,
        )

    with FileProjectSource(source.root) as reader:
        result = asyncio.run(exercise(reader))
    assert len(acknowledgements) == 2 and result.attempts_used == 2
    assert len(factory.calls) == 2 and result.members[0].cases[0].status == "valid"


def test_experiment_report_excludes_proven_unsent_provider_usage(setup, monkeypatch):
    from dataclasses import replace

    import deykit.application.evaluations as evaluation_module
    from deykit.application.evaluations import EvaluationService
    from deykit.application.experiment_reports import experiment_report
    from deykit.application.reports import ReportService
    from deykit.contracts.records import ProviderProfile
    from deykit.providers.choice import JEV_DESTINATION
    from deykit.reports.models import ClassificationPricing, ReportRequest, TokenPrice

    source, runner, factory, clock = setup(count=64)
    factory.profile_value = ProviderProfile(
        id="live",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref="env:UNUSED_TEST_KEY",
    )
    source.commit(
        "provider-config",
        (SourceChange(ResourceKey("providers", "live"), dump_record(factory.profile_value), None),),
    )
    request = experiment(source, budget="1.00").model_copy(
        update={
            "mode": "live",
            "variants": (
                ExperimentVariant(name="live", provider_id="live", reservation_usd="0.10"),
            ),
            "settings": ExecutionSettings(max_attempts=8, concurrency=8),
        }
    )

    async def fail_first(_case_id, _request):
        return DispatchOutcome(
            state="known",
            error=ServiceError(code="provider_auth"),
            provider_wide=True,
            usage_source='{"input_tokens":3,"output_tokens":1}',
        )

    factory.callback = fail_first
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="bulk-failure"))
    report = experiment_report(source.capture_snapshot(), result.group_id)
    usage = report.members[0].usage
    assert isinstance(usage, dict)
    assert usage["dispatched_attempt_count"] == 1
    assert usage["reported_attempt_count"] == 1
    assert usage["total_input_tokens"] == 3
    assert report.members[0].requested_model == "jev-1.13.0"
    assert report.members[0].adapter == "jev"
    assert (
        report.members[0].provider_config_hash
        == runner.repository.history(result.members[0].run_id).manifest.provider_config_hash
    )
    run = result.members[0]
    reports = ReportService(source, clock)
    pricing = ClassificationPricing(
        rates=(
            TokenPrice(
                adapter="jev",
                requested_model="jev-1.13.0",
                currency="USD",
                input_per_million="1",
                output_per_million="1",
                source="test",
                as_of="2026-10-05T00:00:00Z",
            ),
        )
    )
    current_metrics = evaluation_module.metrics_from_frozen
    with monkeypatch.context() as patch:
        patch.setattr(
            evaluation_module,
            "metrics_from_frozen",
            lambda frozen, mode: current_metrics(replace(frozen, group_kind=None), mode),
        )
        legacy = EvaluationService(source, clock).evaluate_saved(
            run.run_id, run.latest_result_snapshot_id, operation_id="legacy-evaluation"
        )
        old_report = reports.create(
            ReportRequest(target_id=legacy.record.id, target_kind="evaluation"),
            operation_id="legacy-report",
        )
    legacy_body = source.read(ResourceKey("evaluations", legacy.record.id)).body
    assert old_report.content.evaluations[0].metrics.usage.dispatched_attempt_count == 8
    implicit = reports.create(
        ReportRequest(target_id=run.run_id, target_kind="run"),
        operation_id="implicit-legacy-report",
    )
    assert implicit.content.target.evaluation_ids == (legacy.record.id,)
    assert implicit.content.evaluations[0].metrics.usage.dispatched_attempt_count == 8
    assert reports.read(old_report.record.id).content == old_report.content
    assert (
        reports.create(
            ReportRequest(target_id=legacy.record.id, target_kind="evaluation"),
            operation_id="legacy-report",
        ).content
        == old_report.content
    )
    assert source.read(ResourceKey("evaluations", legacy.record.id)).body == legacy_body
    explicit_legacy = reports.create(
        ReportRequest(target_id=run.run_id, target_kind="run", evaluation_id=legacy.record.id),
        operation_id="explicit-legacy-report",
    )
    assert explicit_legacy.content.evaluations[0].metrics.usage.dispatched_attempt_count == 8

    evaluation = EvaluationService(source, clock).evaluate_saved(
        run.run_id, run.latest_result_snapshot_id, operation_id="saved-evaluation"
    )
    original_evaluation = source.read(ResourceKey("evaluations", evaluation.record.id)).body
    detailed = reports.create(
        ReportRequest(
            target_id=evaluation.record.id,
            target_kind="evaluation",
            preset="classification",
            pricing=pricing,
        ),
        operation_id="detailed-report",
    )
    projected = detailed.content.evaluations[0]
    assert projected.metrics.usage.dispatched_attempt_count == 1
    assert projected.metrics.usage.total_input_tokens == 3
    assert len(projected.attempts) == 8  # The audit still includes the seven proven non-calls.
    assert detailed.content.classification.evaluations[0].cost.total == "0.000004"
    assert reports.read(detailed.record.id).content == detailed.content
    assert reports.read(old_report.record.id).content == old_report.content
    assert source.read(ResourceKey("evaluations", evaluation.record.id)).body == original_evaluation


def test_experiment_report_discloses_actual_answering_models(setup):
    from deykit.application.experiment_reports import experiment_report
    from deykit.contracts.records import NormalizedAnswer

    source, runner, factory, _ = setup(count=4)
    request = experiment(source, budget="0.40").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            )
        }
    )
    for case_id, model in (("case-00", "model-v1"), ("case-01", "model-v2"), ("case-02", None)):
        factory.responses[case_id] = [
            DispatchOutcome(
                state="known",
                answer=NormalizedAnswer(question_id="q", option_id="yes", reported_model=model),
            )
        ]
    factory.responses["case-03"] = [
        DispatchOutcome(state="known", error=ServiceError(code="provider_rejected"))
    ]
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="models"))
    member = experiment_report(source.capture_snapshot(), result.group_id).members[0]
    assert member.reported_model_counts == {"model-v1": 1, "model-v2": 1}
    assert member.unknown_reported_model_answers == 1
    assert member.status_counts["response_error"] == 1


def test_experiment_report_redacts_model_identity_tokens(setup):
    from deykit.application.experiment_reports import experiment_report
    from deykit.contracts.records import NormalizedAnswer

    source, runner, factory, _ = setup(count=2)
    factory.profile_value = factory.profile_value.model_copy(
        update={"requested_model": "authored-demo Bearer requested-secret"}
    )
    request = experiment(source, budget="0.20").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            )
        }
    )
    for case_id, secret in (("case-00", "answer-secret-one"), ("case-01", "answer-secret-two")):
        factory.responses[case_id] = [
            DispatchOutcome(
                state="known",
                answer=NormalizedAnswer(
                    question_id="q", option_id="yes", reported_model=f"model Bearer {secret}"
                ),
            )
        ]
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="redact"))
    member = experiment_report(source.capture_snapshot(), result.group_id).members[0]
    assert member.requested_model == "authored-demo Bearer [REDACTED]"
    assert member.reported_model_counts == {"model Bearer [REDACTED]": 2}


def test_diagnostics_have_explicit_scopes_and_share_the_budget(setup):
    from deykit.application.experiment_reports import experiment_report

    source, runner, factory, _ = setup(count=2)
    request = experiment(source, budget="0.50").model_copy(
        update={
            "settings": ExecutionSettings(max_attempts=8, concurrency=2),
            "diagnostics": (
                ExperimentRepeat(
                    name="repeat",
                    decision_index=0,
                    cohort_index=0,
                    variant="first",
                    case_ids=("case-00",),
                    count=1,
                ),
                ExperimentOrder(
                    name="order",
                    decision_index=0,
                    cohort_index=0,
                    variant="second",
                    case_ids=("case-01",),
                    orders=2,
                    seed=42,
                ),
            ),
        }
    )
    service = ExperimentService(runner)
    preview = service.preview(request)
    assert preview.initial_requests == 7
    assert [member.purpose for member in preview.member_details] == [
        "main",
        "main",
        "repeat",
        "choice_order",
        "choice_order",
    ]
    result = asyncio.run(service.start(request, operation_id="experiment"))
    assert len(factory.calls) == 5
    assert result.reserved_usd == "0.50"
    assert result.members[2].cases[0].status == "valid"
    assert result.members[3].cases[0].status == "pending"
    report = experiment_report(source.capture_snapshot(), result.group_id)
    repeat, order = report.diagnostics
    assert repeat.name == "repeat" and repeat.independent_cases == 1
    assert repeat.disagreement["numerator"] == 0 and repeat.disagreement["denominator"] == 1
    assert repeat.planned_fresh_requests == 1 and repeat.valid_fresh_answers == 1
    assert order.name == "order" and order.independent_cases == 1
    assert order.disagreement["denominator"] == 0 and order.excluded_cases == 1
    assert order.planned_fresh_requests == 2 and order.valid_fresh_answers == 0


def test_explicit_reuse_records_matching_complete_experiment_without_new_calls(setup):
    source, runner, factory, _ = setup(count=2)
    request = experiment(source, budget="0.40")
    service = ExperimentService(runner)
    original = asyncio.run(service.start(request, operation_id="original"))
    assert len(factory.calls) == 4
    reused_request = request.model_copy(update={"reuse_group_id": original.group_id})
    preview = service.preview(reused_request)
    assert preview.initial_requests == 4
    assert preview.fresh_requests == 0
    assert preview.reused_requests == 4
    assert preview.initial_reservation_usd == "0"

    reused = asyncio.run(service.start(reused_request, operation_id="reuse"))
    assert reused.reuse_id is not None
    assert reused.reused_group_id == original.group_id
    assert reused.fresh_attempts == 0 and reused.reserved_usd == "0"
    assert [member.run_id for member in reused.members] == [
        member.run_id for member in original.members
    ]
    assert len(factory.calls) == 4
    replay = asyncio.run(service.start(reused_request, operation_id="reuse"))
    assert replay.reuse_id == reused.reuse_id and replay.replayed
    assert service.read(reused.reuse_id).reused_group_id == original.group_id
    assert len(factory.calls) == 4


def test_reuse_stays_pinned_and_reports_the_reviewed_configuration(setup):
    from deykit.application.experiment_reports import experiment_report

    source, runner, _, _ = setup(count=1)
    request = experiment(source, budget="0.20")
    service = ExperimentService(runner)
    original = asyncio.run(service.start(request, operation_id="original"))
    reused_request = request.model_copy(
        update={
            "reuse_group_id": original.group_id,
            "settings": ExecutionSettings(max_attempts=9, concurrency=1),
            "variants": (
                ExperimentVariant(
                    name="renamed-first", fixture_set_id="set", reservation_usd="0.25"
                ),
                ExperimentVariant(
                    name="renamed-second", fixture_set_id="set", reservation_usd="0.50"
                ),
            ),
        }
    )
    reused = asyncio.run(service.start(reused_request, operation_id="reuse"))
    pinned = reused.group.snapshot_id
    assert pinned is not None
    asyncio.run(service.resume(original.group_id, operation_id="later-resume"))

    shown = service.read(reused.reuse_id)
    assert shown.group.snapshot_id == pinned
    assert shown.group.attempts_used == 0
    assert shown.group.attempt_limit == 9
    assert shown.group.attempts_remaining == 9
    assert [member.variant.name for member in shown.member_details] == [
        "renamed-first",
        "renamed-second",
    ]
    report = experiment_report(source.capture_snapshot(), reused.reuse_id, shown.group.snapshot_id)
    assert [member.member.variant.name for member in report.members] == [
        "renamed-first",
        "renamed-second",
    ]


def test_variants_can_dispatch_concurrently_within_one_shared_limit(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.20").model_copy(
        update={"settings": ExecutionSettings(max_attempts=2, concurrency=2)}
    )
    both_started = asyncio.Event()
    active = 0
    peak = 0

    async def transport(_case_id, _request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            both_started.set()
        try:
            await asyncio.wait_for(both_started.wait(), 0.3)
        except TimeoutError:
            pass
        active -= 1
        from conftest import answer

        return answer()

    factory.callback = transport
    result = asyncio.run(
        asyncio.wait_for(ExperimentService(runner).start(request, operation_id="parallel"), 3)
    )
    assert peak == 2
    assert result.attempts_used == 2 and result.reserved_usd == "0.20"


def test_next_variant_starts_when_another_variant_finishes(setup):
    from conftest import answer

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.30").model_copy(
        update={
            "settings": ExecutionSettings(max_attempts=3, concurrency=2, deadline_seconds=86400),
            "variants": (
                ExperimentVariant(name="slow", fixture_set_id="set", reservation_usd="0.10"),
                ExperimentVariant(name="quick", fixture_set_id="set", reservation_usd="0.10"),
                ExperimentVariant(name="next", fixture_set_id="set", reservation_usd="0.10"),
            ),
        }
    )

    async def exercise():
        release = asyncio.Event()
        first_two_started = asyncio.Event()
        third_started = asyncio.Event()

        async def dispatch(_case_id, _request):
            if len(factory.calls) == 1:
                await release.wait()
            elif len(factory.calls) == 2:
                first_two_started.set()
            elif len(factory.calls) == 3:
                third_started.set()
            return answer()

        factory.callback = dispatch
        task = asyncio.create_task(ExperimentService(runner).start(request, operation_id="slots"))
        try:
            await asyncio.wait_for(first_two_started.wait(), timeout=5)
            await asyncio.wait_for(third_started.wait(), timeout=5)
            return True
        except TimeoutError:
            return False
        finally:
            release.set()
            await task

    assert asyncio.run(exercise())


@pytest.mark.parametrize("case_count", [2, 64])
def test_running_variant_receives_slots_when_another_finishes(setup, case_count):
    from conftest import answer

    source, runner, factory, _ = setup(count=case_count)
    request = experiment(source, budget="20.00").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            ),
            "cohorts": (
                ExperimentCohort(dataset_id="data"),
                ExperimentCohort(dataset_id="data", case_ids=(f"case-{case_count - 1:02}",)),
            ),
            "settings": ExecutionSettings(
                max_attempts=case_count + 1, concurrency=2, deadline_seconds=86400
            ),
        }
    )

    async def exercise():
        release = asyncio.Event()
        expanded = asyncio.Event()

        async def dispatch(_case_id, _request):
            number = len(factory.calls)
            if number == 1:
                await release.wait()
            elif number == 3:
                expanded.set()
            return answer()

        factory.callback = dispatch
        task = asyncio.create_task(ExperimentService(runner).start(request, operation_id="slots"))
        try:
            await asyncio.wait_for(expanded.wait(), timeout=15)
            return True
        except TimeoutError:
            return False
        finally:
            release.set()
            await task

    assert asyncio.run(exercise())


def test_resume_reclaims_initial_slots_of_completed_members(setup):
    from conftest import answer

    source, runner, factory, _ = setup(count=3)
    request = experiment(source, budget="0.50").model_copy(
        update={
            "variants": (
                ExperimentVariant(name="only", fixture_set_id="set", reservation_usd="0.10"),
            ),
            "cohorts": (
                ExperimentCohort(dataset_id="data", case_ids=("case-00", "case-01")),
                ExperimentCohort(dataset_id="data", case_ids=("case-02",)),
            ),
            "settings": ExecutionSettings(max_attempts=5, concurrency=2, deadline_seconds=86400),
        }
    )

    async def exercise():
        release = asyncio.Event()
        both_started = asyncio.Event()
        retry = False

        async def dispatch(case_id, _request):
            if not retry and case_id != "case-02":
                return DispatchOutcome(
                    state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
                )
            if retry and case_id == "case-00":
                await release.wait()
            if retry and case_id == "case-01":
                both_started.set()
            return answer()

        factory.callback = dispatch
        service = ExperimentService(runner)
        started = await service.start(request, operation_id="start")
        retry = True
        task = asyncio.create_task(
            service.resume(started.group_id, operation_id="resume", retry_unknown=True)
        )
        try:
            await asyncio.wait_for(both_started.wait(), timeout=10)
            return True
        except TimeoutError:
            return False
        finally:
            release.set()
            await task

    assert asyncio.run(exercise())


def test_group_finalization_waits_for_priority_inspection(setup, monkeypatch):
    from deykit.storage import FileProjectSource

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.20")
    service = ExperimentService(runner)

    async def exercise(reader):
        priority = reader.priority_read()

        async def stop_at_deadline(*_args, **_kwargs):
            priority.__enter__()

            async def release():
                await asyncio.sleep(0.1)
                priority.__exit__(None, None, None)

            asyncio.create_task(release())
            return "budget_exhausted", ServiceError(
                code="run_incomplete", reason="segment_deadline"
            )

        monkeypatch.setattr(service.groups, "_execute_experiment", stop_at_deadline)
        return await service.start(request, operation_id="interrupted")

    with FileProjectSource(source.root) as reader:
        result = asyncio.run(exercise(reader))
    assert result.group.snapshot_id is not None
    assert all(member.cases[0].status == "pending" for member in result.members)
    assert not factory.calls


@pytest.mark.parametrize("case_count", [2, 64])
def test_provider_wide_failure_stops_other_variants_before_draining(setup, case_count):
    from conftest import answer

    source, runner, factory, _ = setup(count=case_count)
    request = experiment(source, budget="3.20").model_copy(
        update={"settings": ExecutionSettings(max_attempts=32, concurrency=4)}
    )

    async def exercise():
        release = asyncio.Event()
        failed = asyncio.Event()
        calls_after_failure = 0

        async def dispatch(_case_id, _request):
            nonlocal calls_after_failure
            number = len(factory.calls)
            if number == 1:
                await release.wait()
                return answer()
            if number == 2:
                failed.set()
                return DispatchOutcome(
                    state="known",
                    error=ServiceError(code="provider_auth", reason="auth_failed"),
                    provider_wide=True,
                )
            if failed.is_set():
                calls_after_failure += 1
            return answer()

        factory.callback = dispatch
        task = asyncio.create_task(ExperimentService(runner).start(request, operation_id="failure"))
        await asyncio.wait_for(failed.wait(), 3)
        await asyncio.sleep(0.3)
        release.set()
        await task
        return calls_after_failure

    assert asyncio.run(exercise()) == 0


def test_provider_failure_does_not_stop_or_block_resuming_another_profile(setup):
    from conftest import answer

    from deykit.contracts.records import ProviderProfile
    from deykit.providers.choice import JEV_DESTINATION

    source, runner, factory, _ = setup(count=1)
    profiles = {
        name: ProviderProfile(
            id=name,
            adapter="jev",
            requested_model=model,
            destination=JEV_DESTINATION,
            credential_ref="env:UNUSED_TEST_KEY",
        )
        for name, model in (("bad", "jev-1.13.0"), ("good", "jev-1.14.0"))
    }
    source.commit(
        "providers",
        tuple(
            SourceChange(ResourceKey("providers", name), dump_record(profile), None)
            for name, profile in profiles.items()
        ),
    )
    factory.profile = lambda provider_id, _fixture: profiles[provider_id]
    request = experiment(source, budget="0.30").model_copy(
        update={
            "mode": "live",
            "variants": (
                ExperimentVariant(name="bad", provider_id="bad", reservation_usd="0.10"),
                ExperimentVariant(name="good", provider_id="good", reservation_usd="0.10"),
            ),
            "settings": ExecutionSettings(max_attempts=3, concurrency=2),
        }
    )

    async def exercise():
        good_started = asyncio.Event()
        good_attempts = 0

        async def dispatch(_case_id, compiled):
            nonlocal good_attempts
            if compiled.requested_model == "jev-1.13.0":
                await good_started.wait()
                return DispatchOutcome(
                    state="known", error=ServiceError(code="provider_auth"), provider_wide=True
                )
            good_attempts += 1
            good_started.set()
            if good_attempts == 1:
                return DispatchOutcome(
                    state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
                )
            return answer()

        factory.callback = dispatch
        service = ExperimentService(runner)
        started = await service.start(request, operation_id="provider-start")
        assert started.attempts_used == 2
        preview = service.preview_resume(started.group_id, retry_unknown=True)
        assert preview.retry_unknown
        resumed = await service.resume(
            started.group_id, operation_id="provider-resume", retry_unknown=True
        )
        assert resumed.attempts_used == 3 and resumed.reserved_usd == "0.30"
        assert resumed.members[1].cases[0].status == "valid"
        assert [call[1].requested_model for call in factory.calls].count("jev-1.13.0") == 1
        assert good_attempts == 2

    asyncio.run(exercise())


def test_completed_provider_credentials_are_not_needed_for_resume(setup, monkeypatch):
    from conftest import answer

    from deykit.application.dataset_support import fail
    from deykit.contracts.records import ProviderProfile
    from deykit.providers.choice import JEV_DESTINATION

    source, runner, factory, _ = setup(count=1)
    profiles = {
        name: ProviderProfile(
            id=name,
            adapter="jev",
            requested_model=model,
            destination=JEV_DESTINATION,
            credential_ref="env:UNUSED_TEST_KEY",
        )
        for name, model in (("done", "jev-1.13.0"), ("pending", "jev-1.14.0"))
    }
    source.commit(
        "providers",
        tuple(
            SourceChange(ResourceKey("providers", name), dump_record(profile), None)
            for name, profile in profiles.items()
        ),
    )
    factory.profile = lambda provider_id, _fixture: profiles[provider_id]
    request = experiment(source, budget="0.30").model_copy(
        update={
            "mode": "live",
            "variants": (
                ExperimentVariant(name="done", provider_id="done", reservation_usd="0.10"),
                ExperimentVariant(name="pending", provider_id="pending", reservation_usd="0.10"),
            ),
            "settings": ExecutionSettings(max_attempts=3, concurrency=2),
        }
    )
    pending_attempts = 0

    async def dispatch(_case_id, compiled):
        nonlocal pending_attempts
        if compiled.requested_model == "jev-1.14.0":
            pending_attempts += 1
            if pending_attempts == 1:
                return DispatchOutcome(
                    state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
                )
        return answer()

    factory.callback = dispatch
    service = ExperimentService(runner)
    started = asyncio.run(service.start(request, operation_id="start"))
    resolve = factory.resolve

    def credentials_removed(profile, fixture_id):
        if profile.id == "done":
            fail("credential_unavailable", "preflight_failed")
        return resolve(profile, fixture_id)

    monkeypatch.setattr(factory, "resolve", credentials_removed)
    preview = service.preview_resume(started.group_id, retry_unknown=True)
    assert preview.members[0].eligible_case_ids == ()
    resumed = asyncio.run(
        service.resume(started.group_id, operation_id="resume", retry_unknown=True)
    )
    assert all(member.cases[0].status == "valid" for member in resumed.members)
    assert pending_attempts == 2 and len(factory.calls) == 3


def test_reuse_rejects_changed_inputs_before_dispatch(setup):
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=1)
    request = experiment(source, budget="0.20")
    service = ExperimentService(runner)
    original = asyncio.run(service.start(request, operation_id="original"))
    case_key = ResourceKey("cases", "case-00", ("data",))
    stored = source.read(case_key)
    case = load_record(CaseRecord, stored.body)
    changed = case.model_copy(update={"input_source": '{"text":"different"}'})
    source.commit("edit-input", (SourceChange(case_key, dump_record(changed), stored.etag),))
    reused = request.model_copy(update={"reuse_group_id": original.group_id})
    preview = service.preview(reused)
    assert preview.initial_requests == 2
    assert preview.compatibility_failures[0].error.reason == "experiment_reuse_identity_mismatch"
    assert preview.fresh_requests == 0 and preview.reused_requests == 0
    with pytest.raises(ServiceFailure) as error:
        asyncio.run(service.start(reused, operation_id="changed-reuse"))
    assert error.value.error.reason == "experiment_reuse_identity_mismatch"
    assert len(factory.calls) == 2


def test_unknown_price_cannot_dispatch_with_a_spending_limit(setup):
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=1)
    request = experiment(source).model_copy(
        update={
            "variants": (
                ExperimentVariant(name="unknown", fixture_set_id="set", reservation_usd=None),
            )
        }
    )
    service = ExperimentService(runner)
    preview = service.preview(request)
    assert preview.initial_reservation_usd is None and preview.unknown_price_requests == 1
    with pytest.raises(ServiceFailure) as error:
        asyncio.run(service.start(request, operation_id="unknown"))
    assert error.value.error.reason == "experiment_price_unknown_with_budget"
    assert not factory.calls


def test_preview_lists_compatibility_failures_without_creating_runs(setup):
    source, runner, factory, _ = setup(count=1)
    request = experiment(source)
    factory.error = ServiceError(code="preflight_failed", reason="credential_unavailable")
    before = source.capture_snapshot()
    preview = ExperimentService(runner).preview(request)
    assert preview.group is None
    assert [failure.member_index for failure in preview.compatibility_failures] == [0, 1]
    assert all(
        failure.error.reason == "credential_unavailable"
        for failure in preview.compatibility_failures
    )
    assert preview.unplanned_members == 2
    assert not factory.calls and source.capture_snapshot() == before


def test_preview_retains_expanded_evidence_when_freeze_is_too_large(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=2)
    request = experiment(source)
    service = ExperimentService(runner)

    def oversized(*_args, **_kwargs):
        raise ServiceFailure(ServiceError(code="preflight_failed", reason="record_resource_limit"))

    monkeypatch.setattr(service.groups, "preview", oversized)
    before = source.capture_snapshot()
    preview = service.preview(request)
    assert preview.group is None
    assert preview.initial_requests == 4 and preview.known_reservation_usd == "0.40"
    assert preview.unplanned_members == 0
    assert preview.compatibility_failures[0].error.reason == "record_resource_limit"
    assert source.capture_snapshot() == before and not factory.calls


def test_preview_checks_the_storage_transaction_envelope(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=2)
    service = ExperimentService(runner)
    request = experiment(source)

    def oversized(_changes):
        raise ServiceFailure(ServiceError(code="preflight_failed", reason="record_resource_limit"))

    monkeypatch.setattr(source, "preview_create_transaction", oversized, raising=False)
    before = source.capture_snapshot()
    preview = service.preview(request)
    assert preview.group is None and preview.initial_requests == 4
    assert preview.compatibility_failures[0].error.reason == "record_resource_limit"
    assert source.capture_snapshot() == before and not factory.calls


def test_storage_preflight_rejects_an_oversized_manifest_without_writes(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure
    from deykit.contracts import codec
    from deykit.contracts.json_value import JsonLimits
    from deykit.storage._chunks import ChunkManifest

    source, _, _, _ = setup(count=1)
    before = source.capture_snapshot()
    changes = tuple(
        SourceChange(ResourceKey("prepared_cases", f"case-{index}", ("run",)), b"{}", None)
        for index in range(20)
    )
    original_limits = codec.record_limits
    monkeypatch.setattr(
        codec,
        "record_limits",
        lambda kind: (
            JsonLimits(max_bytes=1_000) if kind is ChunkManifest else original_limits(kind)
        ),
    )
    with pytest.raises(ServiceFailure) as failure:
        source.preview_create_transaction(changes)
    assert failure.value.error.reason == "record_resource_limit"
    assert source.capture_snapshot() == before


def test_report_keeps_pending_cases_in_strict_accuracy_denominator(setup):
    from deykit.application.experiment_reports import experiment_report
    from deykit.application.labels import LabelService

    source, runner, factory, clock = setup(count=2)
    counter = itertools.count()
    labels = LabelService(source, clock, lambda: f"label-{next(counter)}")
    for index in range(2):
        review = labels.read("decision", "data", f"case-{index:02}").review
        labels.set(review, ("yes",), provenance="model_generated", operation_id=f"label-op-{index}")
    request = experiment(source, budget="0.10")
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="start"))
    report = experiment_report(source.capture_snapshot(), result.group_id, result.group.snapshot_id)
    assert sum(member.applicable_expectations for member in report.members) == 4
    assert sum(member.full_cohort_strict_accuracy["numerator"] for member in report.members) == 1
    assert sum(member.full_cohort_strict_accuracy["denominator"] for member in report.members) == 4
    assert sum(member.valid_answer_accuracy["denominator"] for member in report.members) == 1
    assert all(
        member.applicable_label_provenance == {"model_generated": 2} for member in report.members
    )
    assert all(member.excluded_label_provenance == {} for member in report.members)
    assert report.reserved_usd == "0.10" and len(factory.calls) == 1


def test_parallel_bulk_variants_do_not_contend_with_each_other(setup, monkeypatch):
    from deykit.cli.context import SystemClock
    from deykit.runner import scheduler

    source, runner, factory, _ = setup(count=64)
    request = experiment(source, budget="0.20").model_copy(
        update={"settings": ExecutionSettings(max_attempts=2, concurrency=2)}
    )
    runner.repository.clock = SystemClock()
    original_read = source.consistent_read
    main_thread = threading.get_ident()

    @contextmanager
    def slow_read():
        outer = not getattr(source._local, "source_depth", 0)
        with original_read() as captured:
            if outer and threading.get_ident() != main_thread:
                time.sleep(0.06)
            yield captured

    monkeypatch.setattr(source, "consistent_read", slow_read)
    monkeypatch.setattr(scheduler, "_SOURCE_CONTENTION_BUDGET_SECONDS", 0.01)
    monkeypatch.setattr(scheduler, "_SOURCE_CONTENTION_DELAYS_SECONDS", (0.005,))
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="parallel-bulk"))
    assert result.attempts_used == 2 and result.reserved_usd == "0.20"
    assert len(factory.calls) == 2


def test_group_cancellation_checks_reuse_validated_prepared_requests(setup, monkeypatch):
    from deykit.contracts.records import PreparedCase
    from deykit.runner import decoding, history

    source, runner, _factory, _ = setup(count=2)
    request = experiment(source, budget="0.40")
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="start"))
    current = runner.repository.history(result.members[0].run_id)
    segment = current.segments[-1]
    decoded = history.decoded
    calls = []

    def observe(kind, record):
        if kind is PreparedCase:
            calls.append(record.key)
        return decoded(kind, record)

    monkeypatch.setattr(history, "decoded", observe)
    monkeypatch.setattr(decoding, "decoded", observe)
    assert not runner.repository.cancelled(current, segment)
    assert not runner.repository.cancelled(current, segment)
    assert not calls
