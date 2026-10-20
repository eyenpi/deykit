"""Bounded batch publication, durable transport intent, cancellation and explicit resume."""

import asyncio

from conftest import answer
from test_execution import request

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import DispatchOutcome, ExecutionSettings


def test_bulk_publishes_before_transport_and_bounds_transaction_count(setup, monkeypatch):
    source, service, factory, _ = setup(64)
    commits = []
    original = source.commit

    def commit(operation, changes, **kwargs):
        commits.append(len(changes))
        return original(operation, changes, **kwargs)

    monkeypatch.setattr(source, "commit", commit)

    async def transport(case_id, wire):
        # Open another adapter to check durable source, not the runner's in-memory projection.
        from deykit.runner.history import read_history
        from deykit.storage import FileProjectSource

        with FileProjectSource(source.root) as reader:
            (run_id,) = reader.list_ids("runs")
            history = read_history(reader, run_id)
            attempt = history.case_attempts(case_id)[-1]
            assert history.final_event(attempt.id).state == "dispatched"
            assert attempt.request == wire
        return answer()

    factory.callback = transport
    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=64, concurrency=16)),
            operation_id="bulk",
        )
    )
    assert result.state == "completed" and result.attempts_used == 64
    assert len(factory.calls) == 64
    assert len(commits) <= 12  # four preparation batches, four settlements and lifecycle boundaries
    assert all(case.status == "valid" for case in result.cases)
    replay = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=64, concurrency=16)),
            operation_id="bulk",
        )
    )
    assert replay.replayed and replay.run_id == result.run_id and len(factory.calls) == 64


def test_bulk_cancel_drains_inflight_and_resume_does_not_repeat_completed(setup):
    source, service, factory, _ = setup(64)
    run_ids = []
    cancelled = False

    async def transport(_case_id, _wire):
        nonlocal cancelled
        if not cancelled:
            cancelled = True
            service.cancel(run_ids[0], operation_id="cancel")
        await asyncio.sleep(0)
        return answer()

    factory.callback = transport
    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=80, concurrency=8)),
            operation_id="bulk",
            on_created=lambda created: run_ids.append(created.run_id),
        )
    )
    assert result.state == "cancelled"
    calls_before = [case for case, _, _ in factory.calls]
    assert 1 <= len(calls_before) <= 8
    assert all(case.status in {"valid", "pending"} for case in result.cases)
    factory.callback = None
    resumed = asyncio.run(service.resume(result.run_id, operation_id="resume"))
    calls_after = [case for case, _, _ in factory.calls]
    assert resumed.state == "completed"
    assert len(calls_after) == len(set(calls_after)) == 64
    assert resumed.attempts_used <= 80
    assert set(calls_before).issubset(calls_after)


def test_bulk_unknown_is_not_retried_and_lifetime_cap_is_preserved(setup):
    _, service, factory, _ = setup(64)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
        )
    ]
    first = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=64, concurrency=16)),
            operation_id="bulk",
        )
    )
    assert first.exit_code == 4 and len(factory.calls) == 64
    assert service.preview_resume(first.run_id).planned_case_ids == ()
    resumed = asyncio.run(service.resume(first.run_id, operation_id="retry", retry_unknown=True))
    assert resumed.state == "budget_exhausted" and resumed.attempts_used == 64
    assert len(factory.calls) == 64


def test_bulk_storage_work_does_not_block_transport_event_loop(setup, monkeypatch):
    from threading import Event

    _, service, _, _ = setup(64)
    entered, released = Event(), Event()
    prepare = service.repository.prepare_dispatch_many

    def slow_prepare(*args, **kwargs):
        entered.set()
        assert released.wait(1), "repository work blocked the transport event loop"
        return prepare(*args, **kwargs)

    monkeypatch.setattr(service.repository, "prepare_dispatch_many", slow_prepare)

    async def run():
        async def heartbeat():
            while not entered.is_set():
                await asyncio.sleep(0.001)
            released.set()

        beat = asyncio.create_task(heartbeat())
        try:
            return await service.start(
                request(settings=ExecutionSettings(max_attempts=64, concurrency=16)),
                operation_id="bulk-heartbeat",
            )
        finally:
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)

    assert asyncio.run(run()).state == "completed"


def test_bulk_controls_work_through_separate_cli_processes(setup):
    import json
    import subprocess
    import sys
    import time

    from deykit.application.execution import ExecutionService
    from deykit.cli.context import SystemClock

    source, _, factory, _ = setup(64)
    service = ExecutionService(source, source, factory, SystemClock())
    run_ids = []
    ready = asyncio.Event()
    release = asyncio.Event()

    async def transport(_case_id, _wire):
        if len(factory.calls) == 8:
            ready.set()
        await release.wait()
        return answer()

    factory.callback = transport

    def cli(*args):
        started = time.monotonic()
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from deykit.cli.main import app; app()",
                "--project",
                str(source.root),
                "--json",
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        elapsed = time.monotonic() - started
        assert result.returncode == 0, result.stdout + result.stderr
        assert elapsed < 5
        return json.loads(result.stdout)["data"]

    async def run():
        task = asyncio.create_task(
            service.start(
                request(settings=ExecutionSettings(max_attempts=80, concurrency=8)),
                operation_id="bulk-cli",
                on_created=lambda created: run_ids.append(created.run_id),
            )
        )
        try:
            await asyncio.wait_for(ready.wait(), 5)
            shown = await asyncio.to_thread(cli, "runs", "show", run_ids[0])
            assert shown["attempts_used"] == 8
            cancelled = await asyncio.to_thread(
                cli, "runs", "cancel", run_ids[0], "--operation-id", "cancel-cli"
            )
            assert cancelled["run"]["state"] == "cancelling"
            release.set()
            return await asyncio.wait_for(task, 10)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    result = asyncio.run(run())
    assert result.state == "cancelled" and len(factory.calls) == 8
    assert sum(case.status == "valid" for case in result.cases) == 8
    assert sum(case.status == "pending" for case in result.cases) == 56


def test_bulk_uncertain_settlement_commit_is_not_repeated(setup):
    from deykit.contracts.codec import load_record
    from deykit.contracts.records import AttemptEvent

    source, service, factory, _ = setup(64)
    armed = True

    def fail_after_saved_response(point):
        nonlocal armed
        if point != "archived" or not armed:
            return
        for record in source.read_records():
            if record.key.collection == "attempt_events":
                event = load_record(AttemptEvent, record.body)
                if event.state == "known":
                    armed = False
                    raise OSError("injected failure after durable settlement")

    source._hook = fail_after_saved_response
    options = request(settings=ExecutionSettings(max_attempts=64, concurrency=16))
    try:
        asyncio.run(service.start(options, operation_id="uncertain-bulk"))
        raise AssertionError("injected persistence failure was hidden")
    except ServiceFailure as failure:
        assert failure.error.reason == "persistence_failed"
    source._hook = lambda _: None
    (run_id,) = source.list_ids("runs")
    recovered = service.show(run_id)
    assert recovered.state == "interrupted"
    assert sum(case.status == "valid" for case in recovered.cases) == 16
    assert len(factory.calls) == 16
    replay = asyncio.run(service.start(options, operation_id="uncertain-bulk"))
    assert replay.replayed and len(factory.calls) == 16
    resumed = asyncio.run(service.resume(run_id, operation_id="explicit-resume"))
    assert resumed.state == "completed" and resumed.attempts_used == 64
    assert len(factory.calls) == len({case for case, _, _ in factory.calls}) == 64


def test_actual_process_death_during_bulk_transport_keeps_unknowns_explicit(setup, tmp_path):
    from test_process_recovery import CHILD, child_command, kill_at_checkpoint

    source, service, factory, _ = setup(64)
    marker = tmp_path / "bulk-killed"
    command, environment = child_command(source, "in_transport", marker)
    command[2] = CHILD.replace("waiter=clock,hook=hook", "waiter=clock").replace(
        "concurrency=1", "concurrency=8"
    )
    kill_at_checkpoint(command, environment, marker)
    (run_id,) = source.list_ids("runs")
    recovered = service.show(run_id)
    assert recovered.state == "interrupted" and recovered.attempts_used == 8
    assert sum(case.status == "unknown" for case in recovered.cases) == 8
    assert sum(case.status == "pending" for case in recovered.cases) == 56
    assert factory.calls == []
    default = asyncio.run(service.resume(run_id, operation_id="resume-pending"))
    assert default.attempts_used == 64 and len(factory.calls) == 56
    assert sum(case.status == "unknown" for case in default.cases) == 8
    explicit = asyncio.run(service.resume(run_id, operation_id="retry-unknown", retry_unknown=True))
    assert explicit.state == "completed" and explicit.attempts_used == 72
    assert len(factory.calls) == len({case for case, _, _ in factory.calls}) == 64


def test_real_cli_executes_bulk_authored_fixtures(setup):
    import json
    import subprocess
    import sys

    source, _, _, _ = setup(64)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from deykit.cli.main import app; app()",
            "--project",
            str(source.root),
            "--json",
            "run",
            "--decision",
            "decision",
            "--dataset",
            "data",
            "--mode",
            "fixture",
            "--fixture-set",
            "set",
            "--concurrency",
            "16",
            "--attempt-limit",
            "64",
            "--operation-id",
            "cli-bulk",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == 1
    run = envelope["data"]["run"]
    assert run["state"] == "completed" and run["attempts_used"] == 64
    assert sum(case["status"] == "valid" for case in run["cases"]) == 64
    assert run["mode"] == "fixture"


def test_bulk_finalization_failure_retains_run_identity_and_saved_calls(setup, monkeypatch):
    from deykit.contracts.codec import load_record
    from deykit.contracts.records import RunEvent

    source, service, factory, _ = setup(64)
    commit = source.commit

    def fail_after_finish(operation_id, changes, **kwargs):
        receipt = commit(operation_id, changes, **kwargs)
        if any(
            change.key.collection == "run_events"
            and load_record(RunEvent, change.body).state == "completed"
            for change in changes
        ):
            raise ServiceFailure(ServiceError(code="internal_error", reason="storage_io"))
        return receipt

    monkeypatch.setattr(source, "commit", fail_after_finish)
    options = request(settings=ExecutionSettings(max_attempts=64, concurrency=16))
    try:
        asyncio.run(service.start(options, operation_id="finish-error"))
        raise AssertionError("finalization error was hidden")
    except ServiceFailure as failure:
        assert failure.error.reason == "persistence_failed"
        run_id = failure.error.resource_id
        assert run_id is not None
    monkeypatch.setattr(source, "commit", commit)
    assert service.show(run_id).state == "completed"
    assert len(factory.calls) == 64
    assert asyncio.run(service.start(options, operation_id="finish-error")).replayed
    assert len(factory.calls) == 64


def test_bulk_deadline_after_publication_keeps_unsent_cases_pending(setup):
    source, service, factory, clock = setup(64)

    def elapse_after_preparation(point):
        if point == "archived" and any(
            record.key.collection == "attempts" for record in source.read_records()
        ):
            clock.value = 601

    source._hook = elapse_after_preparation
    result = asyncio.run(
        service.start(
            request(
                settings=ExecutionSettings(max_attempts=64, concurrency=64, deadline_seconds=600)
            ),
            operation_id="deadline",
        )
    )
    assert result.state == "budget_exhausted" and result.exit_code == 4
    assert factory.calls == [] and result.attempts_used == 64
    assert all(case.status == "pending" for case in result.cases)


def test_bulk_persistence_failure_still_settles_other_inflight_responses(setup, monkeypatch):
    source, service, factory, _ = setup(64)
    release = asyncio.Event()

    async def transport(case_id, _wire):
        if int(case_id.rsplit("-", 1)[1]) >= 8:
            await release.wait()
        return answer()

    factory.callback = transport
    settle_many = service.repository.settle_many
    failed = False

    async def run():
        loop = asyncio.get_running_loop()

        def fail_once(received):
            nonlocal failed
            if not failed:
                failed = True
                loop.call_soon_threadsafe(release.set)
                raise ServiceFailure(ServiceError(code="internal_error", reason="storage_io"))
            return settle_many(received)

        monkeypatch.setattr(service.repository, "settle_many", fail_once)
        try:
            await service.start(
                request(settings=ExecutionSettings(max_attempts=64, concurrency=16)),
                operation_id="partial-settlement",
            )
            raise AssertionError("persistence failure was hidden")
        except ServiceFailure as failure:
            assert failure.error.reason == "persistence_failed"
            return failure.error.resource_id

    run_id = asyncio.run(run())
    recovered = service.show(run_id)
    assert len(factory.calls) == recovered.attempts_used == 16
    assert sum(case.status == "valid" for case in recovered.cases) == 8
    assert sum(case.status == "unknown" for case in recovered.cases) == 8
    assert sum(case.status == "pending" for case in recovered.cases) == 48


def test_bulk_waiting_transport_does_not_reprocess_unchanged_history(setup, monkeypatch):
    from deykit.application.execution import ExecutionService
    from deykit.cli.context import SystemClock

    source, _, factory, _ = setup(64)
    service = ExecutionService(source, source, factory, SystemClock())
    ready, release = asyncio.Event(), asyncio.Event()
    calls = []
    history = service.repository.history

    def observe(run_id):
        calls.append(run_id)
        return history(run_id)

    monkeypatch.setattr(service.repository, "history", observe)

    async def transport(_case, _wire):
        if len(factory.calls) == 8:
            ready.set()
        await release.wait()
        return answer()

    factory.callback = transport

    async def run():
        task = asyncio.create_task(
            service.start(
                request(settings=ExecutionSettings(max_attempts=64, concurrency=8)),
                operation_id="idle-source",
            )
        )
        try:
            await asyncio.wait_for(ready.wait(), 5)
            before = len(calls)
            await asyncio.sleep(0.2)
            assert len(calls) == before
        finally:
            release.set()
            await task

    asyncio.run(run())


def test_operational_history_reuses_the_admitted_epoch(setup, monkeypatch):
    source, service, _, _ = setup(1)
    result = asyncio.run(service.start(request(), operation_id="view"))
    walks = []
    read_tree = source.files.read_tree

    def observe(parts, visitor, **kwargs):
        if parts == ("source",):
            walks.append(parts)
        return read_tree(parts, visitor, **kwargs)

    monkeypatch.setattr(source.files, "read_tree", observe)
    with source.consistent_read():
        first = service.repository.history(result.run_id)
        second = service.repository.history(result.run_id)
        assert first.results() == second.results()
    assert len(walks) == 1
