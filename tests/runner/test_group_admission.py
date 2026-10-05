"""Independent corruption, immutable-boundary, cancellation and recovery probes."""

import asyncio
from dataclasses import replace

import pytest
from test_execution_groups import request

from deykit.application.diagnostics import (
    ChoiceOrderRequest,
    DiagnosticService,
    diagnostic_snapshot_from_records,
)
from deykit.application.errors import ServiceFailure
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.execution_groups import ExecutionGroupSegment
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DispatchOutcome, RegressionRecord
from deykit.regressions.evidence import admit_regression_origin, regression_hash
from deykit.runner.group_evidence import admit_group_snapshots, content_hash


def changed(records, key, record):
    body = dump_record(record)
    return tuple(
        replace(r, body=body, etag=bytes_hash(body)) if r.key == key else r for r in records
    )


def test_pinned_diagnostic_and_all_retained_corruption_admitted_before_repair(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    snapshot_id = result.group.snapshot_id
    original = diagnostic_snapshot_from_records(source.capture_snapshot(), snapshot_id)
    asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    records = source.capture_snapshot()
    assert diagnostic_snapshot_from_records(records, snapshot_id) == original
    key = ResourceKey("diagnostic_snapshots", snapshot_id)
    snapshot = original.snapshot
    later = next(
        s for s in admit_group_snapshots(records, result.group.group_id) if s.id != snapshot_id
    )
    # Both a rehashed old boundary linked to a later segment and a foreign result are invalid.
    corruptions = [
        snapshot.model_copy(update={"segment_id": later.segment_id}),
        snapshot.model_copy(update={"results": tuple(reversed(snapshot.results))}),
        snapshot.model_copy(update={"results": (snapshot.results[0], snapshot.results[0])}),
        snapshot.model_copy(update={"id": "wrong-path"}),
        snapshot.model_copy(update={"group_id": "absent-group"}),
    ]
    for forged in corruptions:
        forged = forged.model_copy(update={"content_hash": content_hash(forged)})
        batch = changed(records, key, forged)
        # Remove final summary too: malformed retained graph must reject before repair.
        batch = tuple(r for r in batch if r.key != ResourceKey("diagnostic_snapshots", later.id))
        with monkeypatch.context() as patch:
            patch.setattr(
                source, "capture_snapshot", lambda *args, retained=batch, **kwargs: retained
            )
            with pytest.raises(ServiceFailure):
                service.read(result.group.group_id)
        assert source.capture_snapshot() == records
    with pytest.raises(ServiceFailure) as error:
        diagnostic_snapshot_from_records((*records, records[0]), snapshot_id)
    assert error.value.error.reason == "duplicate_captured_key"
    segment_record = next(r for r in records if r.key.collection == "group_segments")
    segment = load_record(ExecutionGroupSegment, segment_record.body)
    forged = segment.model_copy(update={"deadline_at": "2026-10-06T00:00:00Z"})
    with pytest.raises(ServiceFailure):
        admit_group_snapshots(changed(records, segment_record.key, forged), result.group.group_id)
    assert len(factory.calls) == 2


def test_terminal_missing_snapshot_repair_is_idempotent_zero_send(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    snapshot = service.groups.store.snapshot

    def fail_snapshot(*args):
        raise ServiceFailure(ServiceError(code="internal_error", reason="injected_snapshot_io"))

    monkeypatch.setattr(service.groups.store, "snapshot", fail_snapshot)
    with pytest.raises(ServiceFailure):
        asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    assert source.list_ids("diagnostic_snapshots") == () and len(factory.calls) == 2
    members = tuple(
        r
        for r in source.capture_snapshot()
        if r.key.collection in {"runs", "segments", "result_snapshots", "run_events"}
    )
    monkeypatch.setattr(service.groups.store, "snapshot", snapshot)
    group_id = source.list_ids("execution_groups")[0]
    repaired = service.read(group_id)
    assert repaired.summary.independent_case_count == 1
    assert len(source.list_ids("diagnostic_snapshots")) == 1
    assert service.read(group_id).group.snapshot_id == repaired.group.snapshot_id
    assert len(factory.calls) == 2
    assert (
        tuple(
            r
            for r in source.capture_snapshot()
            if r.key.collection in {"runs", "segments", "result_snapshots", "run_events"}
        )
        == members
    )


def test_regression_rehashed_origin_metadata_and_attempt_forgery(setup):
    source, runner, factory, clock = setup(count=1)
    run = asyncio.run(runner.start(request(), operation_id="origin"))
    saved = RegressionService(source, clock, lambda: "reg").add(
        RegressionAdd(
            run_id=run.run_id, case_id="case-00", acceptable_option_ids=("yes",), reason="Oracle"
        ),
        operation_id="save",
    )
    records = source.capture_snapshot()
    record = load_record(RegressionRecord, source.read(ResourceKey("regressions", saved.id)).body)
    for update in (
        {"source_attempt_id": "foreign-attempt"},
        {"decision_revision_id": "foreign-revision"},
        {"source_run_id": "foreign-run"},
        {"source_case": record.source_case.model_copy(update={"tags": ("forged",)})},
    ):
        forged = record.model_copy(update=update)
        forged = forged.model_copy(update={"content_hash": regression_hash(forged)})
        with pytest.raises(ServiceFailure):
            admit_regression_origin(records, forged)
    assert len(factory.calls) == 1 and source.capture_snapshot() == records


def test_group_cancellation_stops_current_child_and_old_cutoff_does_not_cancel_resume(setup):
    from conftest import answer

    source, runner, factory, _ = setup(count=3)
    service = DiagnosticService(runner)
    cancelled = []

    async def callback(case_id, body):
        if not cancelled:
            group_id = source.list_ids("execution_groups")[0]
            progress = service.groups.show(group_id)
            later = progress.members[1].run_id
            runner.cancel(later, operation_id="later-cancel")
            cancelled.append(later)
        return answer()

    factory.callback = callback
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    assert len(factory.calls) == 1
    assert result.exit_code == 4
    assert all(m.state == "cancelled" for m in result.group.members)
    factory.callback = None
    resumed = asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert resumed.exit_code == 0 and len(factory.calls) == 6
    assert resumed.group.attempts_used == 6


def test_provider_wide_failure_resume_zero_write(setup):
    source, runner, factory, _ = setup(count=1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            provider_wide=True,
            error=ServiceError(code="provider_rejected", reason="authentication_failed"),
        )
    ]
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as error:
        asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert error.value.error.reason == "provider_wide_failure_requires_new_run"
    assert len(factory.calls) == 1 and source.capture_snapshot() == before


def test_resume_receipt_inside_source_lock_leaves_lock_before_render(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    real_receipt = source.operation_receipt
    calls = []

    def receipt(operation_id, *, intent_hash):
        calls.append(operation_id)
        # First pre-owner lookup simulates a receipt not yet visible. The second
        # lookup happens inside source ownership and finds the actual committed receipt.
        return None if len(calls) == 1 else real_receipt(operation_id, intent_hash=intent_hash)

    monkeypatch.setattr(source, "operation_receipt", receipt)
    before = source.capture_snapshot()
    replay = asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert replay.group.replayed and len(factory.calls) == 2
    assert source.capture_snapshot() == before


def test_pinned_check_preserves_multiple_oracles_after_removal_and_later_resume(setup):
    from deykit.application.checks import CheckRequest, CheckService, check_snapshot_from_records

    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(request(), operation_id="origin"))
    names = iter(("reg-a", "reg-b", "removal"))
    regressions = RegressionService(source, clock, lambda: next(names))
    for expected in (("yes", "no"), ("no",)):
        regressions.add(
            RegressionAdd(
                run_id=origin.run_id,
                case_id="case-00",
                acceptable_option_ids=expected,
                reason="Explicit separate oracle",
            ),
            operation_id="save-" + expected[0] + str(len(expected)),
        )
    checks = CheckService(runner)
    result = asyncio.run(
        checks.start(
            CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="set"),
            operation_id="check",
        )
    )
    assert result.exit_code == 5 and result.expectation_failures == 1
    assert len(result.cases) == 2 and len(factory.calls) == 2
    assert result.group.independent_case_count == 1 and result.group.initial_requests == 1
    before = check_snapshot_from_records(source.capture_snapshot(), result.group.snapshot_id)
    regressions.remove("reg-a", decision_id="decision", operation_id="remove")
    asyncio.run(checks.resume(result.group.group_id, operation_id="resume"))
    capture = source.capture_snapshot()
    assert check_snapshot_from_records(capture, before.snapshot.id) == before
    assert source.capture_snapshot() == capture and len(factory.calls) == 2


@pytest.mark.parametrize("explicit", [False, True])
def test_regression_removed_between_prepare_and_freeze_conflicts_without_group_write(
    setup, monkeypatch, explicit
):
    from deykit.application.checks import CheckRequest, CheckService

    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(request(), operation_id="origin"))
    regressions = RegressionService(source, clock, lambda: "reg")
    regressions.add(
        RegressionAdd(
            run_id=origin.run_id, case_id="case-00", acceptable_option_ids=("yes",), reason="Oracle"
        ),
        operation_id="save",
    )
    checks = CheckService(runner)
    plan = checks._plan
    after_removal = []

    def prepare(request):
        prepared = plan(request)
        regressions.remove("reg", decision_id="decision", operation_id="remove")
        after_removal.append(source.capture_snapshot())
        return prepared

    monkeypatch.setattr(checks, "_plan", prepare)
    with pytest.raises(ServiceFailure) as error:
        asyncio.run(
            checks.start(
                CheckRequest(
                    decision_id="decision",
                    mode="fixture",
                    fixture_set_id="set",
                    regression_ids=("reg",) if explicit else (),
                ),
                operation_id="check",
            )
        )
    assert error.value.error.code == "conflict"
    assert source.capture_snapshot() == after_removal[0] and len(factory.calls) == 1
    assert not source.list_ids("execution_groups")


def test_legacy_regression_metadata_visible_but_never_current_input_execution(setup):
    from deykit.application.checks import CheckRequest, CheckService
    from deykit.runner.repository import change

    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(request(), operation_id="origin"))
    manifest = runner.repository.history(origin.run_id).manifest
    legacy = RegressionRecord(
        id="legacy",
        decision_revision_id=manifest.decision_revision_id,
        dataset_id="data",
        case_id="case-00",
        question_id="q",
        input_source='{"text":"old"}',
        input_hash="0" * 64,
        acceptable_option_ids=("yes",),
        reason="Legacy oracle",
        created_at=clock.utc_now(),
    )
    source.commit("legacy-save", (change("regressions", legacy),))
    view = RegressionService(source, clock).list("decision")[0]
    assert view.decision_id == "decision" and not view.executable
    assert view.unavailable_reason == "legacy_regression_not_executable"
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as error:
        CheckService(runner).preview(
            CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="set")
        )
    assert error.value.error.reason == "legacy_regression_not_executable"
    assert source.capture_snapshot() == before and len(factory.calls) == 1


def test_production_32mib_whole_freeze_boundary_includes_segment_ready_bytes(setup):
    from deykit.application.dataset_support import safe_hash
    from deykit.contracts.json_value import JsonDocument, dump_json
    from deykit.runner.group_models import GroupPlan
    from deykit.runner.planner import MAX_PLAN_BYTES

    source, runner, factory, _ = setup(count=20)
    service = DiagnosticService(runner).groups
    selected_request = ChoiceOrderRequest(run=request(cap=100))
    selection_source = dump_json(
        {"kind": "choice_order", "request": selected_request.model_dump(mode="json")}
    )
    digest = safe_hash(
        {"command": "execution_group.start", "selection": JsonDocument(selection_source).value}
    )
    small = runner.planner.prepare_orders(selected_request.run, orders=2, seed=0)

    def stage(padding, trailing=0):
        plans = []
        for plan in small:
            cases = tuple(
                c.model_copy(
                    update={
                        "input_source": dump_json({"text": f"Text {i}", "pad": "x" * padding}),
                        "split": "test",
                    }
                )
                for i, c in enumerate(plan.cases)
            )
            prepared = tuple(
                replace(c, input_hash=JsonDocument(case.input_source).content_hash)
                for c, case in zip(plan.prepared, cases, strict=True)
            )
            plans.append(
                replace(
                    plan,
                    cases=cases,
                    prepared=prepared,
                    development_cases=(),
                    development_labels=(),
                )
            )
        group, changes = service.store.stage_freeze(
            GroupPlan("choice_order", tuple(plans), 100, 600),
            "boundary",
            digest,
            selection_source + " " * trailing,
        )
        segment, operational = service.store.stage_segment(
            group, "boundary", 1, False, service._staged(changes), initial=True
        )
        ready = service.store.stage_ready(segment, service._staged((*changes, *operational)))
        return (*changes, *operational, *ready)

    base = stage(800_000)
    base_size = sum(len(c.body or b"") for c in base)
    increase, remainder = divmod(MAX_PLAN_BYTES - base_size, 40)
    exact = stage(800_000 + increase, remainder)
    assert sum(len(c.body or b"") for c in exact) == 32 * 1024 * 1024
    service._check_size(exact)
    with pytest.raises(ServiceFailure) as error:
        service._check_size((*exact, replace(exact[-1], body=b"x")))
    assert error.value.error.reason == "execution_group_resource_limit"
    assert not source.list_ids("runs") and not source.list_ids("execution_groups")
    assert not factory.calls


def test_concurrent_group_reservations_compete_for_last_lifetime_slot(setup):
    from concurrent.futures import ThreadPoolExecutor

    from deykit.application.dataset_support import safe_hash
    from deykit.contracts.json_value import dump_json
    from deykit.runner.group_models import GroupPlan

    source, runner, factory, _ = setup(count=1)
    request_value = ChoiceOrderRequest(run=request(cap=3))
    selection = {"kind": "choice_order", "request": request_value.model_dump(mode="json")}
    service = DiagnosticService(runner).groups
    plans = runner.planner.prepare_orders(request_value.run, orders=4, seed=0)
    digest = safe_hash({"command": "execution_group.start", "selection": selection})
    with source.execution_owner():
        with source.consistent_read():
            group, changes = service.store.stage_freeze(
                GroupPlan("choice_order", plans, 3, 600), "start", digest, dump_json(selection)
            )
            segment, operational = service.store.stage_segment(
                group, "start", 1, False, service._staged(changes), initial=True
            )
            source.commit("start", (*changes, *operational), intent_hash=digest)
            service.store.ready(segment, acknowledge=False)
        first = segment.member_segments[0]
        history = runner.repository.history(first.run_id)
        child = history.segments[-1]
        assert (
            runner.repository.reserve(first.run_id, child, history.work()[0], deadline=600)
            is not None
        )
        # A new explicit unknown-retry segment retains the first reservation.
        with source.consistent_read():
            second, changes = service.store.stage_segment(
                group, "resume", 2, True, source.capture_snapshot(), initial=False
            )
            source.commit("resume", changes)
            service.store.ready(second, acknowledge=True)
        history = runner.repository.history(first.run_id)
        child = history.segments[-1]
        assert (
            runner.repository.reserve(
                first.run_id, child, history.work(retry_unknown=True)[0], deadline=600
            )
            is not None
        )
        selections = []
        for member in second.member_segments:
            h = runner.repository.history(member.run_id)
            selections.append((member.run_id, h.segments[-1], h.work(retry_unknown=True)[0]))

        def reserve(item):
            try:
                return runner.repository.reserve(*item, deadline=600)
            except ServiceFailure as error:
                assert error.error.reason == "source_busy"
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(reserve, selections))
        assert sum(item is not None for item in outcomes) == 1
        assert runner.repository.history(first.run_id).group.used == 3
        assert runner.repository.history(first.run_id).remaining == 0
    assert not factory.calls


def test_group_readiness_legacy_acknowledgement_retains_source_boundary(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    observed = []
    real_ack = source.acknowledge_cancel

    def acknowledge(run_id, segment_id):
        observed.append(getattr(source._local, "source_depth", 0))
        return real_ack(run_id, segment_id)

    monkeypatch.setattr(source, "acknowledge_cancel", acknowledge)
    asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert len(observed) == 2 and min(observed) > 0
    assert len(factory.calls) == 2


def _rehash_group(records, group_id, **updates):
    from deykit.contracts.execution_groups import ExecutionGroup

    key = ResourceKey("execution_groups", group_id)
    stored = next(r for r in records if r.key == key)
    group = load_record(ExecutionGroup, stored.body).model_copy(update=updates)
    group = group.model_copy(update={"content_hash": content_hash(group)})
    return changed(records, key, group)


def _rehash_selection(records, group_id, updates):
    from deykit.application.dataset_support import safe_hash
    from deykit.contracts.execution_groups import ExecutionGroup
    from deykit.contracts.json_value import JsonDocument, dump_json

    group = load_record(
        ExecutionGroup,
        next(r.body for r in records if r.key == ResourceKey("execution_groups", group_id)),
    )
    selection = JsonDocument(group.selection_source).value
    request_value = selection["request"]
    if group.kind == "choice_order":
        request_value = request_value["run"]
    request_value.update(updates)
    selection_source = dump_json(selection)
    return _rehash_group(
        records,
        group_id,
        selection_source=selection_source,
        intent_hash=safe_hash(
            {"command": "execution_group.start", "selection": JsonDocument(selection_source).value}
        ),
    )


def test_rehashed_original_selectors_rejected_before_pinned_read_or_missing_summary_repair(
    setup, monkeypatch
):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request()), operation_id="selector-start")
    )
    group_id = result.group.group_id
    actual = source.capture_snapshot()
    calls = len(factory.calls)
    forged_updates = (
        ("provider_id", "unbacked-profile", "group_provider_selection_mismatch"),
        ("revision_id", "unbacked-revision", "group_revision_selection_mismatch"),
        ("case_ids", ["case-01"], "diagnostic_scope_selection_mismatch"),
        ("split", "test", "diagnostic_scope_selection_mismatch"),
        ("option_order", ["no", "yes"], "diagnostic_selection_override"),
        ("regression_ids", ["unbacked-regression"], "diagnostic_selection_override"),
    )
    for field, value, reason in forged_updates:
        forged = _rehash_selection(actual, group_id, {field: value})
        with pytest.raises(ServiceFailure) as error:
            diagnostic_snapshot_from_records(forged, result.group.snapshot_id)
        assert error.value.error.reason == reason

        missing_final = tuple(
            record for record in forged if record.key.collection != "diagnostic_snapshots"
        )
        with monkeypatch.context() as patch:
            patch.setattr(
                source,
                "capture_snapshot",
                lambda *args, snapshot=missing_final, **kwargs: snapshot,
            )
            with pytest.raises(ServiceFailure) as error:
                service.read(group_id)
            assert error.value.error.reason == reason
        assert source.capture_snapshot() == actual
        assert len(factory.calls) == calls


def test_original_published_revision_profile_and_case_scope_survive_later_draft_label_edits(setup):
    from deykit.contracts.codec import dump_record
    from deykit.contracts.json_value import JsonDocument
    from deykit.contracts.ports import ResourceKey, SourceChange
    from deykit.contracts.records import (
        CaseRecord,
        ChoiceDefinition,
        DecisionDraft,
        DecisionRecord,
        DecisionRevision,
        LabelRecord,
        RunManifest,
    )
    from deykit.domain.definitions import definition_hash
    from deykit.domain.label_identity import label_id

    source, runner, factory, clock = setup(count=2)
    changes = []
    cases = []
    for case_id in ("case-00", "case-01"):
        stored = source.read(ResourceKey("cases", case_id, ("data",)))
        case = load_record(CaseRecord, stored.body).model_copy(update={"split": "test"})
        cases.append(case)
        body = dump_record(case)
        changes.append(SourceChange(stored.key, body, stored.etag))
    draft_stored = source.read(ResourceKey("drafts", "decision"))
    draft = load_record(DecisionDraft, draft_stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    revision = DecisionRevision(
        id="published",
        decision_id="decision",
        definition=definition,
        content_hash=definition_hash(definition),
        created_at=clock.utc_now(),
    )
    changes.append(
        SourceChange(
            ResourceKey("revisions", "published", ("decision",)), dump_record(revision), None
        )
    )
    decision_stored = source.read(ResourceKey("decisions", "decision"))
    decision = load_record(DecisionRecord, decision_stored.body).model_copy(
        update={"latest_revision_id": "published"}
    )
    changes.append(SourceChange(decision_stored.key, dump_record(decision), decision_stored.etag))
    profile = factory.profile_value
    changes.append(SourceChange(ResourceKey("providers", profile.id), dump_record(profile), None))
    source.commit("publish-original", tuple(changes))

    selected = ChoiceOrderRequest(
        run=request(cap=8).model_copy(
            update={
                "provider_id": "authored",
                "revision_id": "published",
                "case_ids": ("case-01", "case-00"),
                "split": "test",
            }
        )
    )
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(selected, operation_id="selected-source"))
    records = source.capture_snapshot()
    first_manifest = load_record(
        RunManifest,
        next(
            record.body
            for record in records
            if record.key == ResourceKey("runs", result.group.members[0].run_id)
        ),
    )
    assert first_manifest.decision_revision_id != "published"
    assert first_manifest.case_ids == ("case-00", "case-01")

    # Historical admission uses the published and frozen selections, not today's draft/labels.
    edited_definition = definition.model_copy(update={"selected_fields": ()})
    edited_draft = draft.model_copy(
        update={"editor_source": dump_record(edited_definition).decode()}
    )
    source.commit(
        "edit-after-run",
        (
            SourceChange(draft_stored.key, dump_record(edited_draft), draft_stored.etag),
            SourceChange(
                ResourceKey("labels", label_id("case-00", "q"), ("decision", "data")),
                dump_record(
                    LabelRecord(
                        id=label_id("case-00", "q"),
                        decision_id="decision",
                        dataset_id="data",
                        case_id="case-00",
                        question_id="q",
                        input_hash=JsonDocument(cases[0].input_source).content_hash,
                        acceptable_option_ids=("no",),
                        provenance="human",
                        updated_at=clock.utc_now(),
                    )
                ),
                None,
            ),
        ),
    )
    assert (
        diagnostic_snapshot_from_records(
            source.capture_snapshot(), result.group.snapshot_id
        ).group.id
        == result.group.group_id
    )


def test_check_profile_and_revision_selectors_rejected_before_missing_summary_repair(
    setup, monkeypatch
):
    from deykit.application.checks import CheckRequest, CheckService, check_snapshot_from_records

    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(request(), operation_id="check-selector-origin"))
    RegressionService(source, clock, lambda: "check-selector-regression").add(
        RegressionAdd(
            run_id=origin.run_id,
            case_id="case-00",
            acceptable_option_ids=("yes",),
            reason="Explicit oracle",
        ),
        operation_id="check-selector-save",
    )
    service = CheckService(runner)
    result = asyncio.run(
        service.start(
            CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="set"),
            operation_id="check-selector-start",
        )
    )
    group_id = result.group.group_id
    actual = source.capture_snapshot()
    calls = len(factory.calls)
    for field, value, reason in (
        ("provider_id", "unbacked-profile", "group_provider_selection_mismatch"),
        ("revision_id", "unbacked-revision", "group_revision_selection_mismatch"),
    ):
        forged = _rehash_selection(actual, group_id, {field: value})
        with pytest.raises(ServiceFailure) as error:
            check_snapshot_from_records(forged, result.group.snapshot_id)
        assert error.value.error.reason == reason
        missing_final = tuple(
            record for record in forged if record.key.collection != "check_snapshots"
        )
        with monkeypatch.context() as patch:
            patch.setattr(
                source,
                "capture_snapshot",
                lambda *args, snapshot=missing_final, **kwargs: snapshot,
            )
            with pytest.raises(ServiceFailure) as error:
                service.read(group_id)
            assert error.value.error.reason == reason
        assert source.capture_snapshot() == actual
        assert len(factory.calls) == calls


def test_omitted_revision_keeps_original_draft_selection_after_current_draft_and_label_edits(
    setup,
):
    from deykit.contracts.codec import dump_record
    from deykit.contracts.json_value import JsonDocument
    from deykit.contracts.ports import ResourceKey, SourceChange
    from deykit.contracts.records import (
        CaseRecord,
        ChoiceDefinition,
        DecisionDraft,
        LabelRecord,
    )
    from deykit.domain.label_identity import label_id

    source, runner, factory, clock = setup(count=1)
    result = asyncio.run(
        DiagnosticService(runner).start(
            ChoiceOrderRequest(run=request()), operation_id="draft-selection"
        )
    )
    draft_stored = source.read(ResourceKey("drafts", "decision"))
    draft = load_record(DecisionDraft, draft_stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    edited_definition = definition.model_copy(update={"selected_fields": ()})
    edited_draft = draft.model_copy(
        update={"editor_source": dump_record(edited_definition).decode()}
    )
    current_case = load_record(
        CaseRecord, source.read(ResourceKey("cases", "case-00", ("data",))).body
    )
    label = LabelRecord(
        id=label_id("case-00", "q"),
        decision_id="decision",
        dataset_id="data",
        case_id="case-00",
        question_id="q",
        input_hash=JsonDocument(current_case.input_source).content_hash,
        acceptable_option_ids=("no",),
        provenance="human",
        updated_at=clock.utc_now(),
    )
    source.commit(
        "edit-current-draft-after-group",
        (
            SourceChange(draft_stored.key, dump_record(edited_draft), draft_stored.etag),
            SourceChange(
                ResourceKey("labels", label.id, ("decision", "data")),
                dump_record(label),
                None,
            ),
        ),
    )
    pinned = diagnostic_snapshot_from_records(source.capture_snapshot(), result.group.snapshot_id)
    assert pinned.group.id == result.group.group_id
    assert len(factory.calls) == 2


def test_rehashed_group_cap_must_match_original_selection_before_pinned_admission(
    setup, monkeypatch
):
    from deykit.application.errors import ServiceFailure

    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request(cap=2)), operation_id="start")
    )
    group_id = result.group.group_id
    actual = source.capture_snapshot()
    forged = _rehash_group(actual, group_id, max_attempts=100)
    with pytest.raises(ServiceFailure) as error:
        diagnostic_snapshot_from_records(forged, result.group.snapshot_id)
    assert error.value.error.reason == "execution_group_cap_selection_mismatch"

    # A forged cap cannot trigger the legitimate missing-final-summary repair.
    missing_final = tuple(r for r in forged if r.key.collection != "diagnostic_snapshots")
    with monkeypatch.context() as patch:
        patch.setattr(source, "capture_snapshot", lambda *args, **kwargs: missing_final)
        with pytest.raises(ServiceFailure) as error:
            service.read(group_id)
        assert error.value.error.reason == "execution_group_cap_selection_mismatch"
    assert source.capture_snapshot() == actual
    assert len(factory.calls) == 2


def test_exact_prepared_body_hash_binds_order_and_matches_independent_sha256(setup, monkeypatch):
    import hashlib
    import json

    from deykit.contracts.execution_groups import ExecutionGroup
    from deykit.contracts.records import AttemptRecord, PreparedCase, RunManifest
    from deykit.runner.group_evidence import member_prepared_hash

    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    actual = source.capture_snapshot()
    group = load_record(
        ExecutionGroup,
        next(
            r.body
            for r in actual
            if r.key == ResourceKey("execution_groups", result.group.group_id)
        ),
    )
    first_id, second_id = (member.run_id for member in group.members)
    first_manifest = load_record(
        RunManifest, next(r.body for r in actual if r.key == ResourceKey("runs", first_id))
    )
    second_manifest = load_record(
        RunManifest, next(r.body for r in actual if r.key == ResourceKey("runs", second_id))
    )
    second_prepared_stored = next(
        r for r in actual if r.key.collection == "prepared_cases" and r.key.scope == (second_id,)
    )
    second_prepared = load_record(PreparedCase, second_prepared_stored.body)
    first_prepared = load_record(
        PreparedCase,
        next(
            r.body
            for r in actual
            if r.key.collection == "prepared_cases" and r.key.scope == (first_id,)
        ),
    )
    assert first_manifest.option_order != second_manifest.option_order

    by_key = {
        r.key: r
        for r in actual
        if r.key.collection == "prepared_cases" and r.key.scope == (second_id,)
    }
    oracle_rows = []
    for case_id in first_manifest.case_ids:
        stored = by_key[ResourceKey("prepared_cases", case_id, (second_id,))]
        oracle_rows.append(
            {
                "key": {
                    "collection": "prepared_cases",
                    "scope": [second_id],
                    "resource_id": case_id,
                },
                "body_sha256": hashlib.sha256(stored.body).hexdigest(),
            }
        )
    payload = {
        "profile": "deykit-group-member-prepared-v1",
        "run_id": second_id,
        "prepared": oracle_rows,
    }
    expected_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert group.members[1].prepared_hash == expected_hash
    second_scope = tuple(r for r in actual if r.key.scope == (second_id,))
    assert member_prepared_hash(second_id, first_manifest.case_ids, second_scope) == expected_hash

    # Rebind both PreparedCase and AttemptRecord to the other order's exact request.
    forged_prepared = second_prepared.model_copy(update={"request": first_prepared.request})
    changed_records = changed(actual, second_prepared_stored.key, forged_prepared)
    attempt_stored = next(
        r for r in changed_records if r.key.collection == "attempts" and r.key.scope == (second_id,)
    )
    attempt = load_record(AttemptRecord, attempt_stored.body)
    changed_attempt = attempt.model_copy(update={"request": first_prepared.request})
    changed_records = changed(changed_records, attempt_stored.key, changed_attempt)
    with pytest.raises(ServiceFailure) as error:
        diagnostic_snapshot_from_records(changed_records, result.group.snapshot_id)
    assert error.value.error.reason == "execution_group_prepared_hash_mismatch"
    missing_final = tuple(r for r in changed_records if r.key.collection != "diagnostic_snapshots")
    with monkeypatch.context() as patch:
        patch.setattr(source, "capture_snapshot", lambda *args, **kwargs: missing_final)
        with pytest.raises(ServiceFailure) as error:
            service.read(result.group.group_id)
        assert error.value.error.reason == "execution_group_prepared_hash_mismatch"
    assert source.capture_snapshot() == actual
    assert len(factory.calls) == 2


def test_prepared_hash_covers_zero_call_input_errors(setup):
    from deykit.contracts.execution_groups import ExecutionGroup
    from deykit.contracts.records import RunManifest
    from deykit.runner.group_evidence import member_prepared_hash

    source, runner, factory, _ = setup(count=1, invalid=(0,))
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request()), operation_id="invalid-input")
    )
    assert not factory.calls
    records = source.capture_snapshot()
    group = load_record(
        ExecutionGroup,
        next(
            r.body
            for r in records
            if r.key == ResourceKey("execution_groups", result.group.group_id)
        ),
    )
    for member in group.members:
        manifest = load_record(
            RunManifest,
            next(r.body for r in records if r.key == ResourceKey("runs", member.run_id)),
        )
        assert (
            member_prepared_hash(
                member.run_id,
                manifest.case_ids,
                tuple(r for r in records if r.key.scope == (member.run_id,)),
            )
            == member.prepared_hash
        )
        assert result.group.identities[group.members.index(member)].requests[0].request_hash is None
    assert result.group.attempts_used == 0
