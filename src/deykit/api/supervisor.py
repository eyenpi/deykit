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

_CANCEL_RETRY_BUDGET_SECONDS = 5.0
_CANCEL_RETRY_DELAYS_SECONDS = (0.01, 0.05, 0.1, 0.2, 0.25)
_SupervisorTarget = tuple[Literal["run", "group"], str, str, Registration, Any, asyncio.Task[Any]]


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
            task = task_holder[0]
            self._preparing.discard(task)
            if not event.replayed:
                self._runs[key] = (registration, service)
                self._run_tasks[key] = task
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
            task = task_holder[0]
            self._preparing.discard(task)
            if not event.replayed:
                self._runs[key] = (registration, service)
                self._run_tasks[key] = task
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
            task = task_holder[0]
            self._preparing.discard(task)
            if not event.replayed:
                self._groups[key] = (registration, service, kind)
                self._group_tasks[key] = task
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
            task = task_holder[0]
            self._preparing.discard(task)
            if not event.replayed:
                self._groups[key] = (registration, service, kind)
                self._group_tasks[key] = task
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
        for preparing_task in preparing:
            if preparing_task in self._preparing and not preparing_task.done():
                preparing_task.cancel()
        if preparing:
            await asyncio.gather(*preparing, return_exceptions=True)

        # A shared monotonic budget bounds only retry waits and attempts. Each
        # distinct owner still gets its initial attempt, and every thread is
        # awaited before shutdown can release retained project sources.
        loop = asyncio.get_running_loop()
        retry_deadline = loop.time() + _CANCEL_RETRY_BUDGET_SECONDS
        targets: list[_SupervisorTarget] = []
        for (registration_id, run_id), (run_registration, run_service) in tuple(self._runs.items()):
            run_task = self._run_tasks.get((registration_id, run_id))
            if run_registration.id == registration_id and run_task is not None:
                targets.append(
                    ("run", registration_id, run_id, run_registration, run_service, run_task)
                )
        for (registration_id, group_id), (group_registration, group_service, _kind) in tuple(
            self._groups.items()
        ):
            group_task = self._group_tasks.get((registration_id, group_id))
            if group_registration.id == registration_id and group_task is not None:
                targets.append(
                    (
                        "group",
                        registration_id,
                        group_id,
                        group_registration,
                        group_service,
                        group_task,
                    )
                )

        def is_current(target: _SupervisorTarget) -> bool:
            category, registration_id, resource_id, _registration, _service, task = target
            owners = self._run_tasks if category == "run" else self._group_tasks
            return owners.get((registration_id, resource_id)) is task and not task.done()

        def cancel_target(target: _SupervisorTarget) -> None:
            _category, _registration_id, resource_id, _registration, service, _task = target
            service.cancel(resource_id, operation_id=f"shutdown-{resource_id[:32]}")

        pending: list[tuple[_SupervisorTarget, int]] = []
        cancellation_failures = False
        for target in targets:
            if not is_current(target):
                continue
            try:
                await asyncio.to_thread(cancel_target, target)
            except ServiceFailure as error:
                if error.error.code == "conflict" and error.error.reason == "source_busy":
                    if is_current(target):
                        pending.append((target, 0))
                else:
                    cancellation_failures = True
            except Exception:
                cancellation_failures = True

        while pending:
            target, delay_index = pending.pop(0)
            if not is_current(target):
                continue
            remaining = retry_deadline - loop.time()
            if remaining <= 0:
                cancellation_failures = True
                continue
            delay = min(
                _CANCEL_RETRY_DELAYS_SECONDS[
                    min(delay_index, len(_CANCEL_RETRY_DELAYS_SECONDS) - 1)
                ],
                remaining,
            )
            owner = target[-1]
            done, _ = await asyncio.wait((owner,), timeout=delay)
            if done or not is_current(target):
                continue
            if loop.time() >= retry_deadline:
                cancellation_failures = True
                continue
            try:
                await asyncio.to_thread(cancel_target, target)
            except ServiceFailure as error:
                if error.error.code == "conflict" and error.error.reason == "source_busy":
                    if is_current(target):
                        pending.append((target, delay_index + 1))
                else:
                    cancellation_failures = True
            except Exception:
                cancellation_failures = True
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        if cancellation_failures:
            raise ServiceFailure(
                ServiceError(code="internal_error", reason="shutdown_cancel_failed")
            )
