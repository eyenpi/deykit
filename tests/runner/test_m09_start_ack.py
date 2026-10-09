"""Durable first-segment admission for callback-bearing run starts."""

import asyncio
from contextlib import contextmanager

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import dump_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, ExecutionSettings
from deykit.runner.history import RunHistory
from deykit.runner.planner import RunRequest, start_intent


def _request() -> RunRequest:
    return RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
        settings=ExecutionSettings(max_attempts=1, concurrency=1),
    )


def test_fresh_callback_runs_after_original_ready_boundary_and_before_dispatch(setup, monkeypatch):
    source, service, factory, _ = setup(1)
    original_read = source.consistent_read
    lock_depth = 0
    callbacks = []

    @contextmanager
    def tracked_read():
        nonlocal lock_depth
        with original_read():
            lock_depth += 1
            try:
                yield
            finally:
                lock_depth -= 1

    monkeypatch.setattr(source, "consistent_read", tracked_read)

    def acknowledge(event):
        callbacks.append(event)
        assert lock_depth == 0
        assert factory.calls == []
        history = service.repository.history(event.run_id)
        segment = service._require_start_ready(history)
        assert segment.sequence == 1
        assert history.attempts == ()

    progress = asyncio.run(
        service.start(_request(), operation_id="start-ready", on_created=acknowledge)
    )

    assert len(callbacks) == 1
    assert callbacks[0].run_id == progress.run_id
    assert callbacks[0].replayed is False
    assert factory.calls


def test_original_ready_receipt_replay_skips_current_planning_and_backend(setup, monkeypatch):
    source, service, factory, _ = setup(1)
    original = asyncio.run(service.start(_request(), operation_id="original-ready"))
    case_key = ResourceKey("cases", "case-00", ("data",))
    stored = source.read(case_key)
    assert stored is not None
    case = load_record(CaseRecord, stored.body)
    edited = case.model_copy(update={"input_source": dump_json({"text": "edited later"})})
    source.commit(
        "edit-current-after-run",
        (SourceChange(case_key, dump_record(edited), stored.etag),),
    )
    dispatch_count = len(factory.calls)

    def reject_current_planning(_request):
        raise AssertionError("original receipt replay planned against current source")

    def reject_current_backend(_profile, _fixture_set_id):
        raise AssertionError("original receipt replay resolved the current backend")

    monkeypatch.setattr(service.planner, "prepare", reject_current_planning)
    monkeypatch.setattr(factory, "resolve", reject_current_backend)
    callbacks = []
    replay = asyncio.run(
        service.start(_request(), operation_id="original-ready", on_created=callbacks.append)
    )

    assert replay.run_id == original.run_id and replay.replayed
    assert callbacks[0].run_id == original.run_id and callbacks[0].replayed
    assert len(factory.calls) == dispatch_count


def test_missing_original_ready_event_rejects_fresh_and_replay_without_repair(setup, monkeypatch):
    source, service, factory, _ = setup(1)
    commit = source.commit

    def fail_ready(operation_id, changes, *, intent_hash=None):
        if any(
            change.key.collection == "run_events"
            and change.body is not None
            and b"segment_ready" in change.body
            for change in changes
        ):
            raise OSError("simulated ready commit failure")
        return commit(operation_id, changes, intent_hash=intent_hash)

    monkeypatch.setattr(source, "commit", fail_ready)
    callbacks = []
    with pytest.raises(ServiceFailure) as fresh:
        asyncio.run(
            service.start(_request(), operation_id="incomplete-start", on_created=callbacks.append)
        )

    assert fresh.value.error.code == "run_incomplete"
    assert fresh.value.error.reason == "start_acknowledgement_incomplete"
    run_id = fresh.value.error.resource_id
    assert run_id is not None
    assert callbacks == [] and factory.calls == []
    before = source.capture_snapshot()

    with pytest.raises(ServiceFailure) as replay:
        asyncio.run(
            service.start(_request(), operation_id="incomplete-start", on_created=callbacks.append)
        )

    assert replay.value.error.code == "run_incomplete"
    assert replay.value.error.resource_id == run_id
    assert source.capture_snapshot() == before
    assert callbacks == [] and factory.calls == []
    legacy = asyncio.run(service.start(_request(), operation_id="incomplete-start"))
    assert legacy.run_id == run_id and legacy.replayed
    assert source.capture_snapshot() == before


def test_unrelated_segment_service_failure_is_not_relabelled_as_missing_ready(setup, monkeypatch):
    _, service, factory, _ = setup(1)

    def fail_segment(*_args, **_kwargs):
        raise ServiceFailure(ServiceError(code="conflict", reason="source_changed"))

    monkeypatch.setattr(service.repository, "segment", fail_segment)
    callbacks = []

    with pytest.raises(ServiceFailure) as raised:
        asyncio.run(
            service.start(_request(), operation_id="segment-conflict", on_created=callbacks.append)
        )

    assert raised.value.error.code == "conflict"
    assert raised.value.error.reason == "source_changed"
    assert callbacks == [] and factory.calls == []


def test_later_ready_segment_cannot_admit_missing_first_ready(setup):
    _, service, factory, _ = setup(1)
    progress = asyncio.run(service.start(_request(), operation_id="ready-history"))
    history = service.repository.history(progress.run_id)
    first = service._require_start_ready(history)
    later = first.model_copy(update={"id": "later-segment", "sequence": 2})
    later_ready = history.events[-1].model_copy(
        update={
            "id": "later-ready",
            "segment_id": later.id,
            "sequence": history.boundary + 1,
            "state": "segment_ready",
        }
    )
    missing_first_ready = tuple(
        event
        for event in history.events
        if event.segment_id != first.id or event.state != "segment_ready"
    )
    with_later_ready = RunHistory(
        manifest=history.manifest,
        prepared=history.prepared,
        segments=(first, later),
        events=(*missing_first_ready, later_ready),
        attempts=history.attempts,
        attempt_events=history.attempt_events,
        controls=history.controls,
        snapshots=history.snapshots,
        group=history.group,
    )

    with pytest.raises(ServiceFailure) as raised:
        service._require_start_ready(with_later_ready)

    assert raised.value.error.code == "run_incomplete"
    assert raised.value.error.reason == "start_acknowledgement_incomplete"
    assert factory.calls


def test_fresh_callback_failure_retains_ready_run_identity_and_does_not_dispatch(setup):
    source, service, factory, _ = setup(1)

    def fail_callback(_event):
        raise RuntimeError("must not escape")

    with pytest.raises(ServiceFailure) as raised:
        asyncio.run(
            service.start(_request(), operation_id="callback-failure", on_created=fail_callback)
        )

    error = raised.value.error
    assert error.code == "internal_error"
    assert error.reason == "created_callback_failed"
    assert error.resource_id is not None
    history = service.repository.history(error.resource_id)
    service._require_start_ready(history)
    assert history.events[-1].state == "interrupted"
    assert history.events[-1].reason is not None
    assert history.events[-1].reason.resource_id == error.resource_id
    assert history.events[-1].reason.reason == "created_callback_failed"
    assert factory.calls == []
    receipt = source.operation_receipt(
        "callback-failure", intent_hash=start_intent(_request(), None)
    )
    assert receipt is not None
    before_replay = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as replay:
        asyncio.run(
            service.start(
                _request(),
                operation_id="callback-failure",
                on_created=fail_callback,
            )
        )
    assert replay.value.error.code == "internal_error"
    assert replay.value.error.reason == "created_callback_failed"
    assert replay.value.error.resource_id == error.resource_id
    assert source.capture_snapshot() == before_replay
    assert factory.calls == []


def test_callback_finish_failure_keeps_safe_original_identity_and_ready_evidence(
    setup, monkeypatch
):
    _, service, factory, _ = setup(1)

    def fail_finish(*_args, **_kwargs):
        raise ServiceFailure(ServiceError(code="conflict", reason="finish_write_failed"))

    monkeypatch.setattr(service.repository, "finish", fail_finish)

    def fail_callback(_event):
        raise RuntimeError("must not escape")

    with pytest.raises(ServiceFailure) as raised:
        asyncio.run(
            service.start(_request(), operation_id="finish-failure", on_created=fail_callback)
        )

    assert raised.value.error.code == "conflict"
    assert raised.value.error.reason == "finish_write_failed"
    assert raised.value.error.resource_id is not None
    history = service.repository.history(raised.value.error.resource_id)
    service._require_start_ready(history)
    assert all(event.state != "interrupted" for event in history.events)
    assert factory.calls == []
