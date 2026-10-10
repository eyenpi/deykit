"""Bounded pre-admission retries for the synchronous CLI cancel command."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from typing import cast

import pytest
import typer

from deykit.application.errors import ServiceFailure
from deykit.application.execution import ExecutionService
from deykit.cli import output as cli_output
from deykit.cli.commands import execution as execution_command
from deykit.cli.context import CliState
from deykit.contracts.errors import ServiceError
from deykit.runner.history import RunHistory
from deykit.storage import FileProjectSource


def _fake_runner(
    source: FileProjectSource,
    *,
    failure: ServiceFailure | None = None,
) -> tuple[ExecutionService, list[tuple[str, str]], list[int], RunHistory]:
    calls: list[tuple[str, str]] = []
    active_depths: list[int] = []
    history = cast(RunHistory, object())

    def cancel(run_id: str, operation_id: str) -> RunHistory:
        assert source._local.source_depth > 0
        calls.append((run_id, operation_id))
        if failure is not None:
            raise failure
        return history

    def active() -> bool:
        active_depths.append(source._local.source_depth)
        return True

    runner = cast(
        ExecutionService,
        SimpleNamespace(
            repository=SimpleNamespace(cancel=cancel),
            execution=SimpleNamespace(execution_active=active),
        ),
    )
    return runner, calls, active_depths, history


def _prepare_cli(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    runner_factory,
    projection,
) -> list[str | None]:
    with FileProjectSource(project, create=True):
        pass
    cli = CliState(project, True)
    monkeypatch.setattr(cli_output, "state", lambda _ctx: cli)
    monkeypatch.setattr(execution_command, "service", runner_factory)
    monkeypatch.setattr(execution_command, "progress_view", projection)
    generated: list[str | None] = []

    def new_id(supplied: str | None) -> str:
        generated.append(supplied)
        return "actual-cancel-operation"

    monkeypatch.setattr(execution_command, "new_operation_id", new_id)
    return generated


def _invoke_cancel(operation_id: str | None = "requested-cancel") -> None:
    execution_command.cancel_run(
        cast(typer.Context, object()), "run-fixed", operation_id=operation_id
    )


def test_m09_cancel_retries_observed_native_source_busy_once_and_projects_after_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    lock_acquired, release_lock = Event(), Event()
    source_busy_reasons: list[str | None] = []
    holders: list[Thread] = []
    sources: list[FileProjectSource] = []
    runners: list[ExecutionService] = []
    body_calls: list[tuple[str, str]] = []
    active_depths: list[int] = []
    history = cast(RunHistory, object())

    def runner_factory(source: FileProjectSource) -> ExecutionService:
        assert source._local.source_depth == 0
        sources.append(source)
        original = source.consistent_read

        @contextmanager
        def observe_busy() -> Iterator[FileProjectSource]:
            try:
                with original() as admitted_source:
                    yield admitted_source
            except ServiceFailure as error:
                if error.error.code == "conflict" and error.error.reason == "source_busy":
                    source_busy_reasons.append(error.error.reason)
                raise

        monkeypatch.setattr(source, "consistent_read", observe_busy)

        def hold_source() -> None:
            with source.consistent_read():
                lock_acquired.set()
                release_lock.wait(timeout=2)

        holder = Thread(target=hold_source, daemon=True)
        holders.append(holder)
        holder.start()
        assert lock_acquired.wait(timeout=2)

        def cancel(run_id: str, op_id: str) -> RunHistory:
            assert source._local.source_depth > 0
            body_calls.append((run_id, op_id))
            return history

        def active() -> bool:
            active_depths.append(source._local.source_depth)
            return True

        runner = cast(
            ExecutionService,
            SimpleNamespace(
                repository=SimpleNamespace(cancel=cancel),
                execution=SimpleNamespace(execution_active=active),
            ),
        )
        runners.append(runner)
        return runner

    def project(history_value: RunHistory, *, active: bool = False) -> dict[str, object]:
        assert history_value is history
        return {"run_id": "run-fixed", "execution_active": active}

    generated = _prepare_cli(
        monkeypatch, tmp_path / "project", runner_factory, project
    )
    actual_sleep = execution_command._sleep
    delays: list[float] = []

    def release_before_retry(seconds: float) -> None:
        delays.append(seconds)
        assert source_busy_reasons == ["source_busy"]
        assert sources[0]._local.source_depth == 0
        release_lock.set()
        holders[0].join(timeout=2)
        assert not holders[0].is_alive()
        actual_sleep(seconds)

    monkeypatch.setattr(execution_command, "_sleep", release_before_retry)
    try:
        _invoke_cancel("requested-cancel")
    finally:
        release_lock.set()
        for holder in holders:
            holder.join(timeout=2)

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["data"] == {
        "operation_id": "actual-cancel-operation",
        "run": {"run_id": "run-fixed", "execution_active": True},
    }
    assert generated == ["requested-cancel"]
    assert len(runners) == 1 and body_calls == [("run-fixed", "actual-cancel-operation")]
    assert source_busy_reasons == ["source_busy"]
    assert delays == [0.01]
    assert active_depths == [0]


def test_m09_cancel_budget_exhaustion_clamps_waits_and_never_enters_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FileProjectSource(tmp_path / "project", create=True) as source:
        attempts = 0
        failures: list[ServiceFailure] = []
        now = 0.0
        sleeps: list[float] = []
        body_calls = 0

        def busy_epoch():
            nonlocal attempts
            attempts += 1
            failure = ServiceFailure(ServiceError(code="conflict", reason="source_busy"))
            failures.append(failure)
            raise failure

        def monotonic() -> float:
            return now

        def sleep(seconds: float) -> None:
            nonlocal now
            sleeps.append(seconds)
            now += seconds

        monkeypatch.setattr(source, "consistent_read", busy_epoch)
        monkeypatch.setattr(execution_command, "_monotonic", monotonic)
        monkeypatch.setattr(execution_command, "_sleep", sleep)

        with pytest.raises(ServiceFailure) as raised:
            with execution_command._cancel_epoch(source):
                body_calls += 1

    assert attempts > 1 and body_calls == 0
    assert raised.value is failures[0]
    assert raised.value.error.code == "conflict"
    assert raised.value.error.reason == "source_busy"
    assert sleeps[:5] == [0.01, 0.05, 0.1, 0.2, 0.25]
    assert all(0 < delay <= 0.25 for delay in sleeps)
    assert sum(sleeps) == pytest.approx(5.0)
    assert sleeps[-1] < 0.25


def test_m09_cancel_nonbusy_acquisition_failure_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FileProjectSource(tmp_path / "project", create=True) as source:
        failure = ServiceFailure(ServiceError(code="internal_error", reason="storage_io"))
        attempts = 0
        sleeps: list[float] = []

        def fail_acquisition():
            nonlocal attempts
            attempts += 1
            raise failure

        monkeypatch.setattr(source, "consistent_read", fail_acquisition)
        monkeypatch.setattr(execution_command, "_sleep", sleeps.append)
        with pytest.raises(ServiceFailure) as raised:
            with execution_command._cancel_epoch(source):
                pytest.fail("an acquisition failure must not enter the cancellation body")

    assert raised.value is failure
    assert attempts == 1 and sleeps == []


def test_m09_cancel_after_entry_source_busy_is_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FileProjectSource(tmp_path / "project", create=True) as source:
        failure = ServiceFailure(ServiceError(code="conflict", reason="source_busy"))
        runner, calls, _, _ = _fake_runner(source, failure=failure)
        sleeps: list[float] = []
        monkeypatch.setattr(execution_command, "_sleep", sleeps.append)

        with pytest.raises(ServiceFailure) as raised:
            execution_command._cancel_history_once(source, runner, "run-fixed", "cancel-fixed")

        assert raised.value is failure
        assert calls == [("run-fixed", "cancel-fixed")]
        assert sleeps == []


def test_m09_cancel_projection_failure_does_not_repeat_admitted_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    runner_data: list[tuple[ExecutionService, list[tuple[str, str]], list[int]]] = []

    def runner_factory(source: FileProjectSource) -> ExecutionService:
        runner, calls, active_depths, _ = _fake_runner(source)
        runner_data.append((runner, calls, active_depths))
        return runner

    def fail_projection(_history: RunHistory, *, active: bool = False) -> object:
        raise ValueError("projection failed")

    _prepare_cli(monkeypatch, tmp_path / "project", runner_factory, fail_projection)
    with pytest.raises(typer.Exit) as raised:
        _invoke_cancel("cancel-projection-error")

    assert raised.value.exit_code == 1
    assert len(runner_data) == 1
    _, calls, active_depths = runner_data[0]
    assert calls == [("run-fixed", "actual-cancel-operation")]
    assert active_depths == [0]
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["error"]["code"] == "internal_error"
