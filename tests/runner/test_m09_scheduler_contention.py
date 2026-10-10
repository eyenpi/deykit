"""Native source-lock contention coverage for the M09 scheduler policy."""

import asyncio
from threading import Event, Thread

import pytest
from conftest import answer
from test_execution import request

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import ExecutionSettings
from deykit.runner.history import read_history


def test_m09_native_lock_contention_keeps_cancel_durable_and_event_loop_responsive(setup):
    source, service, factory, clock = setup(3)
    lock_acquired, release_lock = Event(), Event()
    dispatch_started, release_dispatch = asyncio.Event(), asyncio.Event()
    holder: Thread | None = None
    run_ids: list[str] = []
    heartbeat_ticks = 0

    def after_dispatch(stage, _attempt):
        nonlocal holder
        if stage != "after_dispatch":
            return

        def hold_source():
            with source.consistent_read():
                lock_acquired.set()
                release_lock.wait(timeout=5)

        holder = Thread(target=hold_source)
        holder.start()
        assert lock_acquired.wait(timeout=2)

    service.scheduler.hook = after_dispatch

    async def transport(_case_id, _wire):
        dispatch_started.set()
        await release_dispatch.wait()
        return answer()

    factory.callback = transport

    class ReleaseOnContention:
        async def wait(self, seconds):
            clock.value += seconds
            await asyncio.sleep(0)
            if dispatch_started.is_set() and not release_lock.is_set():
                release_lock.set()
                assert holder is not None
                await asyncio.to_thread(holder.join, 2)
                service.cancel(run_ids[0], operation_id="cancel-during-contention")
                release_dispatch.set()

    service.scheduler.waiter = ReleaseOnContention()

    async def heartbeat(done):
        nonlocal heartbeat_ticks
        while not done.is_set():
            heartbeat_ticks += 1
            await asyncio.sleep(0)

    async def run():
        done = asyncio.Event()
        beat = asyncio.create_task(heartbeat(done))
        task = asyncio.create_task(
            service.start(
                request(settings=ExecutionSettings(concurrency=1)),
                operation_id="start-contention",
                on_created=lambda created: run_ids.append(created.run_id),
            )
        )
        try:
            result = await task
        finally:
            done.set()
            await beat
        return result

    result = asyncio.run(run())

    assert holder is not None and not holder.is_alive()
    assert heartbeat_ticks > 0
    assert len(factory.calls) == 1
    assert result.state == "cancelled" and result.attempts_used == 1
    assert service.show(result.run_id).state == "cancelled"


def test_m09_dispatch_contention_stops_at_original_deadline_without_transport(setup):
    source, service, factory, clock = setup(3)
    lock_acquired, release_lock = Event(), Event()
    holder: Thread | None = None

    def after_intent(stage, _attempt):
        nonlocal holder
        if stage != "after_intent":
            return

        def hold_source():
            with source.consistent_read():
                lock_acquired.set()
                release_lock.wait(timeout=5)

        holder = Thread(target=hold_source)
        holder.start()
        assert lock_acquired.wait(timeout=2)

    service.scheduler.hook = after_intent

    class ReleaseAtDeadline:
        async def wait(self, seconds):
            clock.value += seconds
            await asyncio.sleep(0)
            if clock.value >= 1 and not release_lock.is_set():
                release_lock.set()
                assert holder is not None
                await asyncio.to_thread(holder.join, 2)

    service.scheduler.waiter = ReleaseAtDeadline()
    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(concurrency=1, deadline_seconds=1)),
            operation_id="start-deadline-contention",
        )
    )

    assert holder is not None and not holder.is_alive()
    assert factory.calls == []
    assert result.state == "budget_exhausted"
    assert service.show(result.run_id).state == "budget_exhausted"
    history = read_history(source, result.run_id)
    assert result.attempts_used == 1 and len(history.attempts) == 1
    final_attempt = history.final_event(history.attempts[0].id)
    assert final_attempt is not None and final_attempt.state == "not_sent"
    assert final_attempt.outcome is not None
    assert final_attempt.outcome.error is not None
    assert final_attempt.outcome.error.reason == "segment_deadline"
    assert service.preview_resume(result.run_id).planned_case_ids == (
        "case-01",
        "case-02",
    )


def test_m09_budget_exhaustion_reports_safe_stage_and_run_id(setup):
    source, service, factory, clock = setup(1)
    result = asyncio.run(service.start(request(), operation_id="start-budget-exhaustion"))
    lock_acquired, release_lock = Event(), Event()

    def hold_source():
        with source.consistent_read():
            lock_acquired.set()
            release_lock.wait(timeout=5)

    holder = Thread(target=hold_source)
    holder.start()
    assert lock_acquired.wait(timeout=2)
    service.scheduler.waiter = clock
    calls = []

    try:
        with pytest.raises(ServiceFailure) as raised:
            asyncio.run(
                service.scheduler._source_call(
                    result.run_id, "history", lambda: calls.append("entered")
                )
            )
    finally:
        release_lock.set()
        holder.join(timeout=2)

    assert not holder.is_alive()
    assert calls == []
    assert raised.value.error.code == "internal_error"
    assert raised.value.error.reason == "source_contention_exhausted"
    assert raised.value.error.resource_id == result.run_id
    assert raised.value.stage == "history"


def test_m09_source_busy_after_epoch_entry_is_hard_and_never_retried(setup, monkeypatch):
    source, service, factory, _ = setup(1)
    run_ids = []
    settle_calls = 0

    def fail_after_entry(attempt, outcome, *, duration_seconds=None):
        nonlocal settle_calls
        settle_calls += 1
        assert source._local.source_depth > 0
        raise ServiceFailure(ServiceError(code="conflict", reason="source_busy"))

    monkeypatch.setattr(service.repository, "settle", fail_after_entry)

    with pytest.raises(ServiceFailure) as raised:
        asyncio.run(
            service.start(
                request(),
                operation_id="start-hard-settlement-failure",
                on_created=lambda created: run_ids.append(created.run_id),
            )
        )

    assert settle_calls == 1
    assert len(factory.calls) == 1
    assert raised.value.error.reason == "persistence_failed"
    assert run_ids
    history = read_history(source, run_ids[0])
    assert history.final_event(history.attempts[0].id).state == "dispatched"
