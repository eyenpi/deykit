"""Durable HTTP execution acknowledgements and tracked settlement workers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Literal

from deykit.application.checks import CheckRequest, CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.application.execution_actions import settle_execution
from deykit.contracts.errors import ServiceError
from deykit.runner.group_models import GroupAcknowledged
from deykit.runner.planner import RunRequest
from deykit.runner.views import RunCreated, RunResumed

from .registry import Registration


@dataclass(frozen=True)
class RunAccepted:
    operation_id: str
    run_id: str
    mode: Literal["fixture", "live"]
    replayed: bool
    segment_id: str | None
    progress_path: str


@dataclass(frozen=True)
class GroupAccepted:
    operation_id: str
    group_id: str
    kind: Literal["choice_order", "regression_check"]
    mode: Literal["fixture", "live"]
    replayed: bool
    segment_id: str
    member_run_ids: tuple[str, ...]
    progress_path: str


class ExecutionSupervisor:
    """Own execution tasks after their callers disconnect or stop awaiting."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._preparing: set[asyncio.Task[Any]] = set()
        self._admitting = True
        self._runs: dict[tuple[str, str], tuple[Registration, ExecutionService]] = {}
        self._groups: dict[
            tuple[str, str],
            tuple[
                Registration,
                DiagnosticService | CheckService,
                Literal["choice_order", "regression_check"],
            ],
        ] = {}
        self._run_tasks: dict[tuple[str, str], asyncio.Task[Any]] = {}
        self._group_tasks: dict[tuple[str, str], asyncio.Task[Any]] = {}

    def _start_task(
        self,
        coroutine: Coroutine[Any, Any, Any],
        acknowledged: asyncio.Future[Any],
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        self._preparing.add(task)
        task.add_done_callback(lambda completed: self._consume(completed, acknowledged))
        return task

    def _consume(self, task: asyncio.Task[Any], acknowledged: asyncio.Future[Any]) -> None:
        self._tasks.discard(task)
        self._preparing.discard(task)
        for key, owner in tuple(self._run_tasks.items()):
            if owner is task:
                self._run_tasks.pop(key, None)
                self._runs.pop(key, None)
        for key, owner in tuple(self._group_tasks.items()):
            if owner is task:
                self._group_tasks.pop(key, None)
                self._groups.pop(key, None)
        if task.cancelled():
            self._pre_ack(
                acknowledged,
                ServiceFailure(ServiceError(code="preflight_failed", reason="service_stopping")),
            )
        else:
            error = task.exception()
            if error is not None:
                self._pre_ack(
                    acknowledged,
                    ServiceFailure(ServiceError(code="internal_error", reason="execution_failed")),
                )

    @staticmethod
    def _pre_ack(future: asyncio.Future[Any], error: Exception) -> None:
        if future.done():
            return
        if isinstance(error, ServiceFailure):
            future.set_exception(error)
        else:
            future.set_exception(
                ServiceFailure(ServiceError(code="internal_error", reason="execution_failed"))
            )

    async def start_run(
        self,
        registration: Registration,
        service: ExecutionService,
        request: RunRequest,
        *,
        operation_id: str,
        expected_review_context_hash: str,
        evaluation_service: EvaluationService,
    ) -> RunAccepted:
        if not self._admitting:
            raise ServiceFailure(ServiceError(code="preflight_failed", reason="service_stopping"))
        loop = asyncio.get_running_loop()
        acknowledged: asyncio.Future[RunCreated] = loop.create_future()
        acknowledged.add_done_callback(self._consume_future)
        task_holder: list[asyncio.Task[Any]] = []

        def callback(event: RunCreated) -> None:
            key = (registration.id, event.run_id)
            self._runs[key] = (registration, service)
            if task_holder:
                self._preparing.discard(task_holder[0])
                self._run_tasks[key] = task_holder[0]
            if not acknowledged.done():
                acknowledged.set_result(event)

        async def execute() -> None:
            try:
                result = await service.start(
                    request,
                    operation_id=operation_id,
                    on_created=callback,
                    expected_review_context_hash=expected_review_context_hash,
                )
                await asyncio.to_thread(settle_execution, evaluation_service, result, operation_id)
            except Exception as error:
                self._pre_ack(acknowledged, error)
            except asyncio.CancelledError:
                self._pre_ack(
                    acknowledged,
                    ServiceFailure(
                        ServiceError(code="preflight_failed", reason="service_stopping")
                    ),
                )
                raise

        task_holder.append(self._start_task(execute(), acknowledged))
        try:
            event = await asyncio.shield(acknowledged)
        except asyncio.CancelledError:
            # The HTTP waiter has gone away. The execution task remains service-owned.
            raise
        self._runs[(registration.id, event.run_id)] = (registration, service)
        return RunAccepted(
            operation_id,
            event.run_id,
            event.mode,
            event.replayed,
            None,
            f"/api/v1/projects/{registration.id}/runs/{event.run_id}",
        )

    async def resume_run(
        self,
        registration: Registration,
        service: ExecutionService,
        run_id: str,
        *,
        operation_id: str,
        retry_unknown: bool,
        max_attempts: int | None,
        evaluation_service: EvaluationService,
    ) -> RunAccepted:
        if not self._admitting:
            raise ServiceFailure(ServiceError(code="preflight_failed", reason="service_stopping"))
        loop = asyncio.get_running_loop()
        acknowledged: asyncio.Future[RunResumed] = loop.create_future()
        acknowledged.add_done_callback(self._consume_future)
        task_holder: list[asyncio.Task[Any]] = []

        def callback(event: RunResumed) -> None:
            key = (registration.id, event.run_id)
            self._runs[key] = (registration, service)
            if task_holder:
                self._preparing.discard(task_holder[0])
                self._run_tasks[key] = task_holder[0]
            if not acknowledged.done():
                acknowledged.set_result(event)

        async def execute() -> None:
            try:
                result = await service.resume(
                    run_id,
                    operation_id=operation_id,
                    retry_unknown=retry_unknown,
                    max_attempts=max_attempts,
                    on_resumed=callback,
                )
                await asyncio.to_thread(settle_execution, evaluation_service, result, operation_id)
            except Exception as error:
                self._pre_ack(acknowledged, error)
            except asyncio.CancelledError:
                self._pre_ack(
                    acknowledged,
                    ServiceFailure(
                        ServiceError(code="preflight_failed", reason="service_stopping")
                    ),
                )
                raise

        task_holder.append(self._start_task(execute(), acknowledged))
        event = await asyncio.shield(acknowledged)
        self._runs[(registration.id, event.run_id)] = (registration, service)
        return RunAccepted(
            operation_id,
            event.run_id,
            event.mode,
            event.replayed,
            event.segment_id,
            f"/api/v1/projects/{registration.id}/runs/{event.run_id}",
        )

    async def start_group(
        self,
        registration: Registration,
        service: DiagnosticService | CheckService,
        kind: Literal["choice_order", "regression_check"],
        request: ChoiceOrderRequest | CheckRequest,
        *,
        operation_id: str,
        expected_review_context_hash: str,
    ) -> GroupAccepted:
        if not self._admitting:
            raise ServiceFailure(ServiceError(code="preflight_failed", reason="service_stopping"))
        loop = asyncio.get_running_loop()
        acknowledged: asyncio.Future[GroupAcknowledged] = loop.create_future()
        acknowledged.add_done_callback(self._consume_future)
        task_holder: list[asyncio.Task[Any]] = []

        def callback(event: GroupAcknowledged) -> None:
            key = (registration.id, event.group_id)
            self._groups[key] = (registration, service, kind)
            if task_holder:
                self._preparing.discard(task_holder[0])
                self._group_tasks[key] = task_holder[0]
            if not acknowledged.done():
                acknowledged.set_result(event)

        async def execute() -> None:
            try:
                if kind == "choice_order":
                    assert isinstance(service, DiagnosticService) and isinstance(
                        request, ChoiceOrderRequest
                    )
                    await service.start(
                        request,
                        operation_id=operation_id,
                        expected_review_context_hash=expected_review_context_hash,
                        on_created=callback,
                    )
                else:
                    assert isinstance(service, CheckService) and isinstance(request, CheckRequest)
                    await service.start(
                        request,
                        operation_id=operation_id,
                        expected_review_context_hash=expected_review_context_hash,
                        on_created=callback,
                    )
            except Exception as error:
                self._pre_ack(acknowledged, error)
            except asyncio.CancelledError:
                self._pre_ack(
                    acknowledged,
                    ServiceFailure(
                        ServiceError(code="preflight_failed", reason="service_stopping")
                    ),
                )
                raise

        task_holder.append(self._start_task(execute(), acknowledged))
        event = await asyncio.shield(acknowledged)
        self._groups[(registration.id, event.group_id)] = (registration, service, kind)
        return GroupAccepted(
            operation_id,
            event.group_id,
            event.kind,
            event.mode,
            event.replayed,
            event.segment_id,
            event.member_run_ids,
            f"/api/v1/projects/{registration.id}/"
            f"{'diagnostics' if kind == 'choice_order' else 'checks'}/{event.group_id}",
        )

    async def resume_group(
        self,
        registration: Registration,
        service: DiagnosticService | CheckService,
        kind: Literal["choice_order", "regression_check"],
        group_id: str,
        *,
        operation_id: str,
        retry_unknown: bool,
    ) -> GroupAccepted:
        if not self._admitting:
            raise ServiceFailure(ServiceError(code="preflight_failed", reason="service_stopping"))
        loop = asyncio.get_running_loop()
        acknowledged: asyncio.Future[GroupAcknowledged] = loop.create_future()
        acknowledged.add_done_callback(self._consume_future)
        task_holder: list[asyncio.Task[Any]] = []

        def callback(event: GroupAcknowledged) -> None:
            key = (registration.id, event.group_id)
            self._groups[key] = (registration, service, kind)
            if task_holder:
                self._preparing.discard(task_holder[0])
                self._group_tasks[key] = task_holder[0]
            if not acknowledged.done():
                acknowledged.set_result(event)

        async def execute() -> None:
            try:
                if kind == "choice_order":
                    assert isinstance(service, DiagnosticService)
                    await service.resume(
                        group_id,
                        operation_id=operation_id,
                        retry_unknown=retry_unknown,
                        on_resumed=callback,
                    )
                else:
                    assert isinstance(service, CheckService)
                    await service.resume(
                        group_id,
                        operation_id=operation_id,
                        retry_unknown=retry_unknown,
                        on_resumed=callback,
                    )
            except Exception as error:
                self._pre_ack(acknowledged, error)
            except asyncio.CancelledError:
                self._pre_ack(
                    acknowledged,
                    ServiceFailure(
                        ServiceError(code="preflight_failed", reason="service_stopping")
                    ),
                )
                raise

        task_holder.append(self._start_task(execute(), acknowledged))
        event = await asyncio.shield(acknowledged)
        self._groups[(registration.id, event.group_id)] = (registration, service, kind)
        return GroupAccepted(
            operation_id,
            event.group_id,
            kind,
            event.mode,
            event.replayed,
            event.segment_id,
            event.member_run_ids,
            f"/api/v1/projects/{registration.id}/"
            f"{'diagnostics' if kind == 'choice_order' else 'checks'}/{event.group_id}",
        )

    async def stop_admission(self) -> None:
        self._admitting = False

    @staticmethod
    def _consume_future(future: asyncio.Future[Any]) -> None:
        if not future.cancelled():
            future.exception()

    async def shutdown(self) -> None:
        self._admitting = False
        preparing = tuple(self._preparing)
        for task in preparing:
            task.cancel()
        if preparing:
            await asyncio.gather(*preparing, return_exceptions=True)

        cancellation_failures = False
        for (registration_id, run_id), (registration, service) in tuple(self._runs.items()):
            task = self._run_tasks.get((registration_id, run_id))
            if registration.id != registration_id or task is None or task.done():
                continue
            try:
                await asyncio.to_thread(
                    service.cancel, run_id, operation_id=f"shutdown-{run_id[:32]}"
                )
            except Exception:
                cancellation_failures = True
        for (registration_id, group_id), (registration, service, _kind) in tuple(
            self._groups.items()
        ):
            task = self._group_tasks.get((registration_id, group_id))
            if registration.id != registration_id or task is None or task.done():
                continue
            try:
                await asyncio.to_thread(
                    service.cancel, group_id, operation_id=f"shutdown-{group_id[:32]}"
                )
            except Exception:
                cancellation_failures = True
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        if cancellation_failures:
            raise ServiceFailure(
                ServiceError(code="internal_error", reason="shutdown_cancel_failed")
            )
