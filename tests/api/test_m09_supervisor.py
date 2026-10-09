"""Focused acknowledgement and disconnect behavior for durable HTTP workers."""

import asyncio
from types import SimpleNamespace

import pytest

from deykit.api.registry import Registration
from deykit.api.supervisor import ExecutionSupervisor
from deykit.application.checks import CheckRequest, CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import ExecutionSettings
from deykit.runner.group_models import GroupAcknowledged
from deykit.runner.planner import RunRequest
from deykit.runner.views import RunCreated


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
    ) -> None:
        self.fail_before_ack = fail_before_ack
        self.fail_after_ack = fail_after_ack
        self.defer_ack = defer_ack
        self.fail_cancel = fail_cancel
        self.started = asyncio.Event()
        self.acknowledged = asyncio.Event()
        self.release_ack = asyncio.Event()
        self.wait_forever = asyncio.Event()
        self.cancel_called = asyncio.Event()
        self.loop = None
        self.cancelled_ids = []

    async def start(self, request, *, operation_id, on_created, expected_review_context_hash):
        del request, operation_id, expected_review_context_hash
        self.loop = asyncio.get_running_loop()
        self.started.set()
        if self.fail_before_ack:
            raise ServiceFailure(ServiceError(code="preflight_failed", reason="review_conflict"))
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

    def cancel(self, run_id, *, operation_id):
        del operation_id
        self.cancelled_ids.append(run_id)
        assert self.loop is not None
        self.loop.call_soon_threadsafe(self.cancel_called.set)
        if self.fail_cancel:
            raise RuntimeError("cancel persistence unavailable")
        self.loop.call_soon_threadsafe(self.wait_forever.set)


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

    async def _ack(self, callback) -> None:
        self.loop = asyncio.get_running_loop()
        self.started.set()
        await self.release_ack.wait()
        self.ack_index += 1
        callback(
            GroupAcknowledged(
                "group-1",
                "choice_order" if isinstance(self, _DiagnosticLifecycle) else "regression_check",
                "fixture",
                f"segment-{self.ack_index}",
                self.ack_index > 1,
                ("member-a", "member-b"),
            )
        )
        self.acknowledged.set()
        await self.finished.wait()

    async def _resume(self, callback) -> None:
        await self._ack(callback)

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
        del operation_id, expected_review_context_hash
        assert isinstance(request, ChoiceOrderRequest)
        await self._ack(on_created)

    async def resume(self, group_id, *, operation_id, retry_unknown, on_resumed):
        del operation_id, retry_unknown
        assert group_id == "group-1"
        await self._resume(on_resumed)


class _CheckLifecycle(_GroupLifecycle, CheckService):
    async def start(
        self,
        request,
        *,
        operation_id,
        expected_review_context_hash,
        on_created,
    ):
        del operation_id, expected_review_context_hash
        assert isinstance(request, CheckRequest)
        await self._ack(on_created)

    async def resume(self, group_id, *, operation_id, retry_unknown, on_resumed):
        del operation_id, retry_unknown
        assert group_id == "group-1"
        await self._resume(on_resumed)


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
                operation_id=f"resume-{kind}",
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

        workers = tuple(supervisor._tasks)
        await supervisor.shutdown()
        assert service.cancelled_ids == ["group-1"]
        assert len(workers) == 2
        assert all(task.done() and not task.cancelled() for task in workers)
        assert supervisor._tasks == set()

    asyncio.run(scenario())
