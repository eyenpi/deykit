"""Focused acknowledgement and disconnect behavior for durable HTTP workers."""

import asyncio
from threading import Event
from types import SimpleNamespace

import pytest

from deykit.api import supervisor as supervisor_module
from deykit.api.registry import Registration
from deykit.api.supervisor import ExecutionSupervisor
from deykit.application.checks import CheckRequest, CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import ExecutionSettings
from deykit.runner.group_models import GroupAcknowledged
from deykit.runner.planner import RunRequest
from deykit.runner.views import RunCreated, RunResumed
from deykit.storage import FileProjectSource


def _registration(registration_id: str = "project") -> Registration:
    return Registration(
        id=registration_id,
        source=None,
        display_path=f"/{registration_id}",
        project_id=f"p-{registration_id}",
    )  # type: ignore[arg-type]


class _RunService:
    def __init__(
        self,
        *,
        fail_before_ack: bool = False,
        fail_after_ack: bool = False,
        defer_ack: bool = False,
        fail_cancel: bool = False,
        busy_cancel_attempts: int = 0,
    ) -> None:
        self.fail_before_ack = fail_before_ack
        self.fail_after_ack = fail_after_ack
        self.defer_ack = defer_ack
        self.fail_cancel = fail_cancel
        self.busy_cancel_attempts = busy_cancel_attempts
        self.cancel_attempts = 0
        self.cancel_operation_ids = []
        self.durable_cancelled_ids = []
        self.settle_after_busy = False
        self.replay_operations = set()
        self.started = asyncio.Event()
        self.acknowledged = asyncio.Event()
        self.release_ack = asyncio.Event()
        self.wait_forever = asyncio.Event()
        self.resume_wait_forever = asyncio.Event()
        self.cancel_called = asyncio.Event()
        self.loop = None
        self.cancelled_ids = []

    async def start(self, request, *, operation_id, on_created, expected_review_context_hash):
        del request, expected_review_context_hash
        self.loop = asyncio.get_running_loop()
        self.started.set()
        if self.fail_before_ack:
            raise ServiceFailure(ServiceError(code="preflight_failed", reason="review_conflict"))
        if operation_id in self.replay_operations:
            on_created(RunCreated("run-1", "fixture", True))
            return SimpleNamespace(
                run_id="run-1",
                latest_result_snapshot_id=None,
                execution_active=False,
                exit_code=0,
            )
        if self.defer_ack:
            await self.release_ack.wait()
        on_created(RunCreated("run-1", "fixture", False))
        self.acknowledged.set()
        if self.fail_after_ack:
            raise RuntimeError("post_ack_failure")
        await self.wait_forever.wait()
        return SimpleNamespace(
            run_id="run-1",
            latest_result_snapshot_id=None,
            execution_active=False,
            exit_code=0,
        )

    async def resume(
        self,
        run_id,
        *,
        operation_id,
        retry_unknown,
        max_attempts,
        on_resumed,
    ):
        del retry_unknown, max_attempts
        assert run_id == "run-1"
        self.loop = asyncio.get_running_loop()
        self.started.set()
        if operation_id in self.replay_operations:
            on_resumed(RunResumed("run-1", "segment-2", "fixture", True))
            return SimpleNamespace(
                run_id="run-1",
                latest_result_snapshot_id=None,
                execution_active=False,
                exit_code=0,
            )
        on_resumed(RunResumed("run-1", "segment-2", "fixture", False))
        self.acknowledged.set()
        await self.resume_wait_forever.wait()
        return SimpleNamespace(
            run_id="run-1",
            latest_result_snapshot_id=None,
            execution_active=False,
            exit_code=0,
        )

    def cancel(self, run_id, *, operation_id):
        self.cancelled_ids.append(run_id)
        self.cancel_attempts += 1
        self.cancel_operation_ids.append(operation_id)
        assert self.loop is not None
        self.loop.call_soon_threadsafe(self.cancel_called.set)
        if self.fail_cancel:
            raise RuntimeError("cancel persistence unavailable")
        if self.cancel_attempts <= self.busy_cancel_attempts:
            if self.settle_after_busy:
                self.loop.call_soon_threadsafe(self.wait_forever.set)
            raise ServiceFailure(ServiceError(code="conflict", reason="source_busy"))
        self.durable_cancelled_ids.append(run_id)
        self.loop.call_soon_threadsafe(self.wait_forever.set)
        self.loop.call_soon_threadsafe(self.resume_wait_forever.set)


class _EvaluationService:
    pass


class _GroupLifecycle:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release_ack = asyncio.Event()
        self.acknowledged = asyncio.Event()
        self.finished = asyncio.Event()
        self.loop = None
        self.cancelled_ids = []
        self.ack_index = 0

    async def _ack(self, callback, operation_id) -> None:
        self.loop = asyncio.get_running_loop()
        self.started.set()
        replayed = operation_id.startswith("replay-")
        await self.release_ack.wait()
        self.ack_index += 1
        callback(
            GroupAcknowledged(
                "group-1",
                "choice_order" if isinstance(self, _DiagnosticLifecycle) else "regression_check",
                "fixture",
                f"segment-{self.ack_index}",
                replayed,
                ("member-a", "member-b"),
            )
        )
        self.acknowledged.set()
        if not replayed:
            await self.finished.wait()

    async def _resume(self, callback, operation_id) -> None:
        await self._ack(callback, operation_id)

    def cancel(self, group_id, *, operation_id):
        del operation_id
        self.cancelled_ids.append(group_id)
        assert self.loop is not None
        self.loop.call_soon_threadsafe(self.finished.set)


class _DiagnosticLifecycle(_GroupLifecycle, DiagnosticService):
    async def start(
        self,
        request,
        *,
        operation_id,
        expected_review_context_hash,
        on_created,
    ):
        del expected_review_context_hash
        assert isinstance(request, ChoiceOrderRequest)
        await self._ack(on_created, operation_id)

    async def resume(self, group_id, *, operation_id, retry_unknown, on_resumed):
        del retry_unknown
        assert group_id == "group-1"
        await self._resume(on_resumed, operation_id)


class _CheckLifecycle(_GroupLifecycle, CheckService):
    async def start(
        self,
        request,
        *,
        operation_id,
        expected_review_context_hash,
        on_created,
    ):
        del expected_review_context_hash
        assert isinstance(request, CheckRequest)
        await self._ack(on_created, operation_id)

    async def resume(self, group_id, *, operation_id, retry_unknown, on_resumed):
        del retry_unknown
        assert group_id == "group-1"
        await self._resume(on_resumed, operation_id)


def _group_request(kind):
    if kind == "choice_order":
        run = RunRequest(
            decision_id="decision",
            dataset_id="dataset",
            mode="fixture",
            fixture_set_id="fixtures",
            settings=ExecutionSettings(max_attempts=4, concurrency=1),
        )
        return ChoiceOrderRequest(run=run, orders=2)
    return CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="fixtures")


def test_pre_ack_failure_never_becomes_an_accepted_response():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(fail_before_ack=True)
        with pytest.raises(ServiceFailure) as raised:
            await supervisor.start_run(
                _registration(),
                service,
                object(),
                operation_id="start-1",
                expected_review_context_hash="0" * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        assert raised.value.error.reason == "review_conflict"
        await supervisor.shutdown()

    asyncio.run(scenario())


def test_post_ack_failure_does_not_rewrite_the_acknowledgement():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(fail_after_ack=True)
        accepted = await supervisor.start_run(
            _registration(),
            service,
            object(),
            operation_id="start-2",
            expected_review_context_hash="1" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )
        assert accepted.run_id == "run-1" and accepted.segment_id is None
        await service.started.wait()
        await asyncio.sleep(0)
        assert accepted.progress_path.endswith("/runs/run-1")
        assert supervisor._runs == {}
        assert supervisor._run_tasks == {}
        assert supervisor._tasks == set()
        await supervisor.shutdown()

    asyncio.run(scenario())


def test_cancelled_http_waiter_keeps_worker_until_durable_shutdown_cancel():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(defer_ack=True)
        waiter = asyncio.create_task(
            supervisor.start_run(
                _registration(),
                service,
                object(),
                operation_id="start-3",
                expected_review_context_hash="2" * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        )
        await service.started.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        service.release_ack.set()
        await service.acknowledged.wait()
        worker = next(iter(supervisor._tasks))
        assert not worker.done()
        await supervisor.shutdown()
        assert not worker.cancelled()
        assert service.cancelled_ids == ["run-1"]
        assert worker.done()

    asyncio.run(scenario())


def test_shutdown_cancels_pre_ack_preparation_without_fabricating_acceptance():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(defer_ack=True)
        waiter = asyncio.create_task(
            supervisor.start_run(
                _registration(),
                service,
                object(),
                operation_id="start-preparing",
                expected_review_context_hash="3" * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        )
        await service.started.wait()

        await supervisor.shutdown()

        with pytest.raises(ServiceFailure) as failed:
            await waiter
        assert failed.value.error.reason == "service_stopping"
        assert service.cancelled_ids == []
        assert supervisor._tasks == set()

    asyncio.run(scenario())


def test_shutdown_failure_does_not_cancel_acknowledged_worker():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(fail_cancel=True)
        await supervisor.start_run(
            _registration(),
            service,
            object(),
            operation_id="start-cancel-failure",
            expected_review_context_hash="4" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )
        worker = next(iter(supervisor._tasks))
        await service.started.wait()

        async def release_after_failed_cancel() -> None:
            await service.cancel_called.wait()
            service.wait_forever.set()

        release = asyncio.create_task(release_after_failed_cancel())

        with pytest.raises(ServiceFailure) as failed:
            await supervisor.shutdown()
        await release

        assert failed.value.error.reason == "shutdown_cancel_failed"
        assert not worker.cancelled()
        assert worker.done()

    asyncio.run(scenario())


def test_stopped_admission_rejects_reservations_without_creating_tasks():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        await supervisor.stop_admission()

        with pytest.raises(ServiceFailure) as failed:
            await supervisor.start_run(
                _registration(),
                _RunService(),
                object(),
                operation_id="after-stop",
                expected_review_context_hash="5" * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )

        assert failed.value.error.reason == "service_stopping"
        assert supervisor._tasks == set()

    asyncio.run(scenario())


def test_shutdown_cancels_two_accepted_runs_and_stops_new_reservations():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        services = (_RunService(), _RunService())
        registrations = (_registration("project-a"), _registration("project-b"))
        for index, (registration, service) in enumerate(zip(registrations, services, strict=True)):
            await supervisor.start_run(
                registration,
                service,
                object(),
                operation_id=f"start-two-{index}",
                expected_review_context_hash=str(index) * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        await asyncio.gather(*(service.started.wait() for service in services))

        await supervisor.shutdown()

        assert [service.cancelled_ids for service in services] == [["run-1"], ["run-1"]]
        assert supervisor._tasks == set()
        with pytest.raises(ServiceFailure) as failed:
            await supervisor.start_run(
                _registration("project-c"),
                _RunService(),
                object(),
                operation_id="start-after-shutdown",
                expected_review_context_hash="6" * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        assert failed.value.error.reason == "service_stopping"

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["choice_order", "regression_check"])
def test_group_callback_survives_disconnect_and_resume_uses_callback_identity(kind):
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        registration = _registration()
        service = _DiagnosticLifecycle() if kind == "choice_order" else _CheckLifecycle()
        waiter = asyncio.create_task(
            supervisor.start_group(
                registration,
                service,
                kind,
                _group_request(kind),
                operation_id=f"start-{kind}",
                expected_review_context_hash="7" * 64,
            )
        )
        await service.started.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        service.release_ack.set()
        await service.acknowledged.wait()
        worker = next(iter(supervisor._tasks))
        assert not worker.done()
        assert supervisor._groups[(registration.id, "group-1")] == (
            registration,
            service,
            kind,
        )

        service.release_ack.clear()
        service.started.clear()
        service.acknowledged.clear()
        resumed_waiter = asyncio.create_task(
            supervisor.resume_group(
                registration,
                service,
                kind,
                "group-1",
                operation_id=f"replay-resume-{kind}",
                retry_unknown=True,
            )
        )
        await service.started.wait()
        service.release_ack.set()
        await service.acknowledged.wait()
        resumed = await resumed_waiter
        assert resumed.segment_id == "segment-2"
        assert resumed.member_run_ids == ("member-a", "member-b")
        assert resumed.progress_path.endswith(
            f"/{'diagnostics' if kind == 'choice_order' else 'checks'}/group-1"
        )
        assert resumed.replayed

        key = (registration.id, "group-1")
        assert supervisor._group_tasks[key] is worker
        assert supervisor._groups[key] == (registration, service, kind)
        assert supervisor._tasks == {worker}
        workers = tuple(supervisor._tasks)
        await supervisor.shutdown()
        assert service.cancelled_ids == ["group-1"]
        assert workers == (worker,)
        assert all(task.done() and not task.cancelled() for task in workers)
        assert supervisor._tasks == set()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("method", "kind"),
    [
        ("start_run", None),
        ("resume_run", None),
        ("start_group", "choice_order"),
        ("start_group", "regression_check"),
        ("resume_group", "choice_order"),
        ("resume_group", "regression_check"),
    ],
)
def test_replay_acknowledgements_never_replace_held_fresh_owner(method, kind):
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        registration = _registration()
        service = (
            _RunService()
            if kind is None
            else _DiagnosticLifecycle()
            if kind == "choice_order"
            else _CheckLifecycle()
        )
        if kind is not None:
            service.release_ack.set()

        async def invoke(operation_id):
            if method == "start_run":
                return await supervisor.start_run(
                    registration,
                    service,
                    object(),
                    operation_id=operation_id,
                    expected_review_context_hash="8" * 64,
                    evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
                )
            if method == "resume_run":
                return await supervisor.resume_run(
                    registration,
                    service,
                    "run-1",
                    operation_id=operation_id,
                    retry_unknown=True,
                    max_attempts=None,
                    evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
                )
            if method == "start_group":
                return await supervisor.start_group(
                    registration,
                    service,
                    kind,
                    _group_request(kind),
                    operation_id=operation_id,
                    expected_review_context_hash="9" * 64,
                )
            return await supervisor.resume_group(
                registration,
                service,
                kind,
                "group-1",
                operation_id=operation_id,
                retry_unknown=True,
            )

        await invoke(f"fresh-{method}")
        key = (registration.id, "run-1" if kind is None else "group-1")
        original = supervisor._run_tasks[key] if kind is None else supervisor._group_tasks[key]
        assert original in supervisor._tasks and not original.done()

        for index in range(10):
            replay_id = f"replay-{method}-{index}"
            service.replay_operations.add(replay_id)
            replayed = await invoke(replay_id)
            assert replayed.replayed is True
            await asyncio.sleep(0)
            owners = supervisor._run_tasks if kind is None else supervisor._group_tasks
            assert owners[key] is original
            assert original in supervisor._tasks and not original.done()

        await supervisor.shutdown()
        assert service.cancelled_ids == ["run-1" if kind is None else "group-1"]
        assert supervisor._tasks == set()
        assert supervisor._preparing == set()
        assert supervisor._runs == {}
        assert supervisor._groups == {}
        assert supervisor._run_tasks == {}
        assert supervisor._group_tasks == {}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("method", "kind"),
    [
        ("start_run", None),
        ("resume_run", None),
        ("start_group", "choice_order"),
        ("start_group", "regression_check"),
        ("resume_group", "choice_order"),
        ("resume_group", "regression_check"),
    ],
)
def test_replay_only_acknowledgement_does_not_claim_external_owner(method, kind):
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        registration = _registration()
        service = (
            _RunService()
            if kind is None
            else _DiagnosticLifecycle()
            if kind == "choice_order"
            else _CheckLifecycle()
        )
        service.replay_operations.add("replay-external")
        if kind is not None:
            service.release_ack.set()
        if method == "start_run":
            accepted = await supervisor.start_run(
                registration,
                service,
                object(),
                operation_id="replay-external",
                expected_review_context_hash="a" * 64,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        elif method == "resume_run":
            accepted = await supervisor.resume_run(
                registration,
                service,
                "run-1",
                operation_id="replay-external",
                retry_unknown=True,
                max_attempts=None,
                evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
            )
        elif method == "start_group":
            accepted = await supervisor.start_group(
                registration,
                service,
                kind,
                _group_request(kind),
                operation_id="replay-external",
                expected_review_context_hash="b" * 64,
            )
        else:
            accepted = await supervisor.resume_group(
                registration,
                service,
                kind,
                "group-1",
                operation_id="replay-external",
                retry_unknown=True,
            )
        assert accepted.replayed is True
        await asyncio.sleep(0)
        await supervisor.shutdown()
        assert service.cancelled_ids == []
        assert supervisor._tasks == set()
        assert supervisor._preparing == set()
        assert supervisor._runs == {}
        assert supervisor._groups == {}
        assert supervisor._run_tasks == {}
        assert supervisor._group_tasks == {}

    asyncio.run(scenario())


def test_fresh_resume_replaces_owner_and_old_completion_cannot_remove_it():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        registration = _registration()
        service = _RunService()
        await supervisor.start_run(
            registration,
            service,
            object(),
            operation_id="fresh-start",
            expected_review_context_hash="c" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )
        key = (registration.id, "run-1")
        old_owner = supervisor._run_tasks[key]

        await supervisor.resume_run(
            registration,
            service,
            "run-1",
            operation_id="fresh-resume",
            retry_unknown=True,
            max_attempts=None,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )
        new_owner = supervisor._run_tasks[key]
        assert new_owner is not old_owner and not new_owner.done()

        service.wait_forever.set()
        await old_owner
        assert supervisor._run_tasks[key] is new_owner
        assert supervisor._runs[key] == (registration, service)

        await supervisor.shutdown()
        assert service.cancelled_ids == ["run-1"]
        assert supervisor._tasks == set()
        assert supervisor._run_tasks == {}
        assert supervisor._runs == {}

    asyncio.run(scenario())


def test_source_busy_cancellation_retries_asynchronously_with_same_operation_id():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(busy_cancel_attempts=2)
        await supervisor.start_run(
            _registration(),
            service,
            object(),
            operation_id="busy-retry-start",
            expected_review_context_hash="d" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )
        ticks = 0
        finished = asyncio.Event()

        async def heartbeat() -> None:
            nonlocal ticks
            while not finished.is_set():
                ticks += 1
                await asyncio.sleep(0.001)

        heartbeat_task = asyncio.create_task(heartbeat())
        await supervisor.shutdown()
        finished.set()
        await heartbeat_task

        assert ticks > 0
        assert service.cancel_attempts == 3
        assert service.cancel_operation_ids == ["shutdown-run-1"] * 3
        assert service.durable_cancelled_ids == ["run-1"]
        assert supervisor._tasks == set()
        assert supervisor._run_tasks == {}
        assert supervisor._runs == {}

    asyncio.run(scenario())


def test_native_source_lock_retry_keeps_loop_responsive_and_persists_after_release(tmp_path):
    async def scenario() -> None:
        source = FileProjectSource(tmp_path / "native-source", create=True)
        lock_acquired = Event()
        release_lock = Event()

        def hold_source_lock() -> None:
            with source.consistent_read():
                lock_acquired.set()
                if not release_lock.wait(timeout=5):
                    raise AssertionError("test did not release native source lock")

        holder = asyncio.create_task(asyncio.to_thread(hold_source_lock))
        assert await asyncio.to_thread(lock_acquired.wait, 1)

        class NativeLockRunService(_RunService):
            def __init__(self) -> None:
                super().__init__()
                self.durable_cancelled_ids = []

            def cancel(self, run_id, *, operation_id):
                self.cancelled_ids.append(run_id)
                self.cancel_attempts += 1
                self.cancel_operation_ids.append(operation_id)
                assert self.loop is not None
                self.loop.call_soon_threadsafe(self.cancel_called.set)
                with source.consistent_read():
                    self.durable_cancelled_ids.append((run_id, operation_id))
                self.loop.call_soon_threadsafe(self.wait_forever.set)

        supervisor = ExecutionSupervisor()
        service = NativeLockRunService()
        await supervisor.start_run(
            _registration(),
            service,
            object(),
            operation_id="native-lock-start",
            expected_review_context_hash="1" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )
        ticks = 0
        stop_heartbeat = asyncio.Event()

        async def heartbeat() -> None:
            nonlocal ticks
            while not stop_heartbeat.is_set():
                ticks += 1
                await asyncio.sleep(0.001)

        heartbeat_task = asyncio.create_task(heartbeat())
        shutdown = asyncio.create_task(supervisor.shutdown())
        await service.cancel_called.wait()
        await asyncio.sleep(0.02)
        release_lock.set()
        await shutdown
        stop_heartbeat.set()
        await heartbeat_task
        await holder

        assert ticks > 0
        assert service.cancel_attempts >= 2
        assert service.cancel_operation_ids == ["shutdown-run-1"] * service.cancel_attempts
        assert service.durable_cancelled_ids == [("run-1", "shutdown-run-1")]
        assert supervisor._tasks == set()
        assert supervisor._run_tasks == {}
        assert supervisor._runs == {}
        source.close()

    asyncio.run(scenario())


def test_owner_settling_after_source_busy_drains_without_claiming_cancellation():
    async def scenario() -> None:
        supervisor = ExecutionSupervisor()
        service = _RunService(busy_cancel_attempts=10)
        service.settle_after_busy = True
        await supervisor.start_run(
            _registration(),
            service,
            object(),
            operation_id="settled-busy-start",
            expected_review_context_hash="e" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )

        await supervisor.shutdown()

        assert service.cancel_attempts == 1
        assert service.cancelled_ids == ["run-1"]
        assert service.durable_cancelled_ids == []
        assert supervisor._tasks == set()
        assert supervisor._run_tasks == {}
        assert supervisor._runs == {}

    asyncio.run(scenario())


def test_active_owner_busy_retry_budget_expiry_errors_after_drain(monkeypatch):
    async def scenario() -> None:
        monkeypatch.setattr(supervisor_module, "_CANCEL_RETRY_BUDGET_SECONDS", 0.025)
        monkeypatch.setattr(supervisor_module, "_CANCEL_RETRY_DELAYS_SECONDS", (0.005,))
        supervisor = ExecutionSupervisor()
        service = _RunService(busy_cancel_attempts=100)
        await supervisor.start_run(
            _registration(),
            service,
            object(),
            operation_id="busy-budget-start",
            expected_review_context_hash="f" * 64,
            evaluation_service=_EvaluationService(),  # type: ignore[arg-type]
        )

        async def finish_after_budget() -> None:
            await asyncio.sleep(0.05)
            service.wait_forever.set()

        release = asyncio.create_task(finish_after_budget())
        with pytest.raises(ServiceFailure) as failed:
            await supervisor.shutdown()
        await release

        assert failed.value.error.reason == "shutdown_cancel_failed"
        assert service.cancel_attempts > 1
        assert supervisor._tasks == set()
        assert supervisor._run_tasks == {}
        assert supervisor._runs == {}

    asyncio.run(scenario())
