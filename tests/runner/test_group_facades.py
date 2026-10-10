"""Captured group acknowledgement and lifecycle facade boundaries."""

import asyncio
from dataclasses import replace

import pytest
from test_execution_groups import request

from deykit.application.checks import CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.execution_groups import ExecutionGroupSegment
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.records import RunEvent


def test_group_acknowledgement_uses_original_ready_segment_and_callback_precedes_dispatch(
    setup, monkeypatch
):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    acknowledgements = []
    order = []
    original_active = runner.execution.execution_active

    def observe_active():
        assert source._local.source_depth == 0
        order.append("active")
        return original_active()

    monkeypatch.setattr(runner.execution, "execution_active", observe_active)

    def acknowledge(event):
        assert source._local.source_depth == 0
        assert order[-1] == "active"
        order.append("callback")
        if event.replayed:
            assert len(factory.calls) == 2
        else:
            assert not factory.calls
        acknowledgements.append(event)

    result = asyncio.run(
        service.start(
            ChoiceOrderRequest(run=request()), operation_id="group-start", on_created=acknowledge
        )
    )
    first = acknowledgements[0]
    assert not first.replayed
    assert first.group_id == result.group.group_id
    assert first.kind == "choice_order" and first.mode == "fixture"
    assert first.member_run_ids == tuple(member.run_id for member in result.group.members)

    replay = asyncio.run(
        service.start(
            ChoiceOrderRequest(run=request()), operation_id="group-start", on_created=acknowledge
        )
    )
    assert replay.group.replayed
    assert acknowledgements[1].replayed
    assert acknowledgements[1].segment_id == first.segment_id
    assert acknowledgements[1].member_run_ids == first.member_run_ids
    assert len(factory.calls) == 2


def test_group_acknowledgement_requires_every_child_ready_event(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request()), operation_id="group-start")
    )
    original_capture = source.capture_snapshot
    records = original_capture()
    segments = tuple(
        load_record(ExecutionGroupSegment, item.body)
        for item in records
        if item.key.collection == "group_segments"
    )
    original_segment = next(item for item in segments if item.sequence == 1)
    linked = original_segment.member_segments[0]
    missing_ready_id = next(
        load_record(RunEvent, item.body).id
        for item in records
        if (
            item.key.collection == "run_events"
            and item.key.scope == (linked.run_id,)
            and load_record(RunEvent, item.body).state == "segment_ready"
            and load_record(RunEvent, item.body).segment_id == linked.segment_id
        )
    )

    def without_typed_readiness():
        fake = []
        for item in records:
            if item.key.collection == "run_events" and item.key.scope == (linked.run_id,):
                event = load_record(RunEvent, item.body)
                if event.id == missing_ready_id:
                    event = event.model_copy(update={"state": "running"})
                    body = dump_record(event)
                    item = replace(item, body=body, etag=bytes_hash(body))
            fake.append(item)
        return tuple(fake)

    monkeypatch.setattr(
        source,
        "capture_snapshot",
        without_typed_readiness,
    )
    active_probes = []
    monkeypatch.setattr(
        runner.execution,
        "execution_active",
        lambda: active_probes.append(True) or False,
    )
    callbacks = []
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(
                ChoiceOrderRequest(run=request()),
                operation_id="group-start",
                on_created=callbacks.append,
            )
        )
    assert failure.value.error.code == "run_incomplete"
    assert failure.value.error.reason == "group_acknowledgement_incomplete"
    assert failure.value.error.resource_id == result.group.group_id
    assert not callbacks and len(factory.calls) == 2
    assert not active_probes
    assert original_capture() == records


def test_missing_group_receipt_does_not_probe_execution_activity(setup, monkeypatch):
    _source, runner, _factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    active_probes = []
    monkeypatch.setattr(
        runner.execution,
        "execution_active",
        lambda: active_probes.append(True) or False,
    )
    assert (
        service.groups._capture_acknowledgement(
            "missing-operation", "0" * 64, command="start", replayed=True
        )
        is None
    )
    assert not active_probes


def test_acknowledgement_callback_failure_keeps_ready_group_without_dispatch(setup):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)

    def fail_callback(_event):
        raise RuntimeError("private callback detail")

    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(
                ChoiceOrderRequest(run=request()),
                operation_id="group-start",
                on_created=fail_callback,
            )
        )
    assert failure.value.error.code == "internal_error"
    assert failure.value.error.reason == "group_created_callback_failed"
    assert failure.value.error.resource_id == source.list_ids("execution_groups")[0]
    assert "private callback detail" not in str(failure.value.error)
    assert len(source.list_ids("execution_groups")) == 1
    assert not factory.calls


def test_resume_callback_acknowledges_original_segment_on_replay(setup):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request()), operation_id="group-start")
    )
    acknowledgements = []

    def acknowledge(event):
        assert source._local.source_depth == 0
        assert len(factory.calls) == 2
        acknowledgements.append(event)

    first = asyncio.run(
        service.resume(
            result.group.group_id,
            operation_id="group-resume",
            on_resumed=acknowledge,
        )
    )
    replay = asyncio.run(
        service.resume(
            result.group.group_id,
            operation_id="group-resume",
            on_resumed=acknowledge,
        )
    )
    assert acknowledgements[0].group_id == result.group.group_id
    assert not acknowledgements[0].replayed
    assert acknowledgements[1].replayed
    assert acknowledgements[1].segment_id == acknowledgements[0].segment_id
    assert first.group.replayed is False and replay.group.replayed
    assert len(factory.calls) == 2


def test_resume_receipt_admits_kind_before_show_or_recovery(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    diagnostic = DiagnosticService(runner)
    result = asyncio.run(
        diagnostic.start(ChoiceOrderRequest(run=request()), operation_id="group-start")
    )
    asyncio.run(diagnostic.resume(result.group.group_id, operation_id="shared-resume"))
    before = source.capture_snapshot()

    check = CheckService(runner)
    monkeypatch.setattr(check.groups, "show", lambda *_args, **_kwargs: pytest.fail("show called"))
    active_probes = []
    monkeypatch.setattr(
        runner.execution,
        "execution_active",
        lambda: active_probes.append(True) or False,
    )
    with pytest.raises(ServiceFailure) as preview_failure:
        check.preview_resume(result.group.group_id)
    assert preview_failure.value.error.reason == "regression_check_group_required"
    assert not active_probes
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(check.resume(result.group.group_id, operation_id="shared-resume"))
    assert failure.value.error.reason == "regression_check_group_required"
    assert not active_probes
    assert source.capture_snapshot() == before
    assert len(factory.calls) == 2


def test_resume_preview_is_captured_zero_write_and_cancel_replays_child_controls(
    setup, monkeypatch
):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request()), operation_id="group-start")
    )
    before = source.capture_snapshot()
    active_probes = []
    original_active = runner.execution.execution_active

    def observe_active():
        assert source._local.source_depth == 0
        active_probes.append(True)
        return original_active()

    monkeypatch.setattr(runner.execution, "execution_active", observe_active)
    preview = service.preview_resume(result.group.group_id)
    assert len(active_probes) == 1
    assert preview.dry_run
    assert preview.group.attempt_limit == result.group.attempt_limit
    assert preview.proposed_attempt_limit == result.group.attempt_limit
    assert preview.members[0].run_id == result.group.members[0].run_id
    assert preview.segment_ids == (
        next(
            load_record(ExecutionGroupSegment, item.body).id
            for item in before
            if item.key.collection == "group_segments"
        ),
    )
    assert source.capture_snapshot() == before

    cancelled = service.cancel(result.group.group_id, operation_id="cancel-group")
    after_cancel = source.capture_snapshot()
    replayed = service.cancel(result.group.group_id, operation_id="cancel-group")
    assert replayed == cancelled
    assert source.capture_snapshot() == after_cancel
    assert len(factory.calls) == 2
