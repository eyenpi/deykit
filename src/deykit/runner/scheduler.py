"""Bounded async scheduling; durable intent precedes every single transport call."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import AttemptRecord, DispatchOutcome, NormalizedAnswer, RunSegment
from deykit.runner.history import RunHistory
from deykit.runner.ports import Backend, Waiter
from deykit.runner.repository import RunRepository, RunState

_SOURCE_CONTENTION_BUDGET_SECONDS = 5.0
_SOURCE_CONTENTION_DELAYS_SECONDS = (0.01, 0.05, 0.1, 0.2, 0.25)
_RepositoryStage = Literal[
    "history",
    "cancel_observation",
    "reservation",
    "dispatch_transition",
    "settlement",
    "finalization",
]
_RepositoryResult = TypeVar("_RepositoryResult")


class AsyncWaiter:
    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass
class Stop:
    state: RunState | None = None
    reason: ServiceError | None = None
    persistence_failed: bool = False
    contention_failure: ServiceError | None = None
    contention_stage: _RepositoryStage | None = None
    unsettled_contention: bool = False


class _SourceContentionExhausted(ServiceFailure):
    def __init__(self, run_id: str, stage: _RepositoryStage) -> None:
        self.stage = stage
        super().__init__(
            ServiceError(
                code="internal_error",
                resource_id=run_id,
                reason="source_contention_exhausted",
            )
        )


class _RepositoryOperationFailure(ServiceFailure):
    def __init__(self, run_id: str, stage: _RepositoryStage) -> None:
        self.stage = stage
        super().__init__(
            ServiceError(code="internal_error", resource_id=run_id, reason="persistence_failed")
        )


class _SegmentDeadlineElapsed(Exception):
    """A bounded reservation/dispatch acquisition reached its original deadline."""


def _outcome(value: DispatchOutcome) -> DispatchOutcome:
    """No serializer sees an unvalidated transport-created model instance."""
    if type(value) is not DispatchOutcome:
        raise ValueError("invalid_transport_outcome")
    raw = dict(vars(value))
    for name, kind in (("answer", NormalizedAnswer), ("error", ServiceError)):
        item = raw.get(name)
        if item is not None:
            if type(item) is not kind:
                raise ValueError("invalid_transport_outcome")
            raw[name] = dict(vars(item))
    for item in [raw, *(node for node in raw.values() if isinstance(node, dict))]:
        for field in item.values():
            if isinstance(field, str):
                field.encode("utf-8", "strict")
    return DispatchOutcome.model_validate(raw)


class Scheduler:
    def __init__(
        self,
        repository: RunRepository,
        *,
        waiter: Waiter | None = None,
        hook: Callable[[str, AttemptRecord], None] | None = None,
    ) -> None:
        self.repository = repository
        self.waiter = waiter or AsyncWaiter()
        self.hook = hook or (lambda _stage, _attempt: None)

    @staticmethod
    def _record_contention(stop: Stop, error: _SourceContentionExhausted) -> None:
        if stop.contention_failure is None:
            stop.contention_failure = error.error
            stop.contention_stage = error.stage
        stop.state = "interrupted"
        stop.reason = error.error
        if error.stage == "settlement":
            stop.unsettled_contention = True

    async def _source_call(
        self,
        run_id: str,
        stage: _RepositoryStage,
        operation: Callable[[], _RepositoryResult],
        *,
        deadline: float | None = None,
    ) -> _RepositoryResult:
        """Retry only source-lock acquisition, never a callable that entered its epoch."""
        repo = self.repository
        budget_deadline = repo.clock.monotonic() + _SOURCE_CONTENTION_BUDGET_SECONDS
        delay_index = 0
        while True:
            now = repo.clock.monotonic()
            if deadline is not None and now >= deadline and deadline <= budget_deadline:
                raise _SegmentDeadlineElapsed
            if delay_index and now >= budget_deadline:
                raise _SourceContentionExhausted(run_id, stage)
            if deadline is not None and now >= deadline:
                raise _SegmentDeadlineElapsed
            entered = False
            try:
                with repo.source.consistent_read():
                    entered = True
                    return operation()
            except ServiceFailure as error:
                if entered or error.error.code != "conflict" or error.error.reason != "source_busy":
                    raise
                now = repo.clock.monotonic()
                if deadline is not None and now >= deadline:
                    raise _SegmentDeadlineElapsed from None
                if now >= budget_deadline:
                    raise _SourceContentionExhausted(run_id, stage) from None
                delay = _SOURCE_CONTENTION_DELAYS_SECONDS[
                    min(delay_index, len(_SOURCE_CONTENTION_DELAYS_SECONDS) - 1)
                ]
                remaining = budget_deadline - now
                if deadline is not None:
                    remaining = min(remaining, deadline - now)
                await self.waiter.wait(min(delay, remaining))
                delay_index += 1
            except Exception:
                raise _RepositoryOperationFailure(run_id, stage) from None

    async def _dispatch(
        self,
        attempt: AttemptRecord,
        segment: RunSegment,
        backend: Backend,
        stop: Stop,
        timeout: int,
        deadline: float,
    ) -> DispatchOutcome:
        repo = self.repository
        started: float | None = None
        duration: float | None = None
        outcome: DispatchOutcome
        cancelled = False
        try:
            if stop.state is not None:
                outcome = DispatchOutcome(
                    state="not_sent",
                    error=ServiceError(code="run_incomplete", reason="cancelled_before_dispatch"),
                )
            else:
                try:
                    dispatched = await self._source_call(
                        attempt.run_id,
                        "dispatch_transition",
                        lambda: repo.dispatched(attempt, segment, deadline=deadline),
                        deadline=deadline,
                    )
                except _SegmentDeadlineElapsed:
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(
                        code="run_incomplete", resource_id=attempt.run_id, reason="segment_deadline"
                    )
                    outcome = DispatchOutcome(state="not_sent", error=stop.reason)
                except _SourceContentionExhausted as error:
                    self._record_contention(stop, error)
                    outcome = DispatchOutcome(state="not_sent", error=error.error)
                else:
                    if not dispatched:
                        outcome = DispatchOutcome(
                            state="not_sent",
                            error=ServiceError(
                                code="run_incomplete", reason="cancelled_before_dispatch"
                            ),
                        )
                    else:
                        self.hook("after_dispatch", attempt)
                        started = repo.clock.monotonic()
                        async with asyncio.timeout(timeout):
                            outcome = _outcome(
                                await backend.for_case(attempt.case_id).dispatch(
                                    attempt.request, timeout_seconds=timeout
                                )
                            )
                        duration = max(0.0, repo.clock.monotonic() - started)
                        self.hook("after_received", attempt)
        except asyncio.CancelledError:
            cancelled = True
            outcome = DispatchOutcome(
                state="unknown",
                error=ServiceError(code="run_incomplete", reason="dispatch_cancelled"),
            )
        except TimeoutError:
            outcome = DispatchOutcome(
                state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
            )
        except _SourceContentionExhausted as error:
            self._record_contention(stop, error)
            return DispatchOutcome(state="unknown", error=error.error)
        except ServiceFailure:
            stop.persistence_failed = True
            stop.state = "interrupted"
            stop.reason = ServiceError(code="internal_error", reason="persistence_failed")
            return DispatchOutcome(state="unknown", error=stop.reason)
        except (Exception, ValidationError):
            # A plugin/transport exception may contain a body or credential. Never
            # persist its repr, traceback or exception arguments.
            outcome = DispatchOutcome(
                state="unknown",
                error=ServiceError(code="provider_rejected", reason="transport_failure"),
            )
        if outcome.provider_wide:
            stop.state = "completed_with_errors"
            stop.reason = outcome.error
        settlement_duration = (
            duration
            if duration is not None
            else max(0.0, repo.clock.monotonic() - started)
            if started is not None
            else None
        )
        try:
            await self._source_call(
                attempt.run_id,
                "settlement",
                lambda: repo.settle(
                    attempt,
                    outcome,
                    duration_seconds=settlement_duration,
                ),
            )
        except _SourceContentionExhausted as error:
            self._record_contention(stop, error)
            stop.unsettled_contention = True
        except ServiceFailure:
            stop.persistence_failed = True
            stop.state = "interrupted"
            stop.reason = ServiceError(code="internal_error", reason="persistence_failed")
        if cancelled:
            raise asyncio.CancelledError
        return outcome

    async def run(
        self,
        history: RunHistory,
        segment: RunSegment,
        backend: Backend,
        *,
        progress: Callable[[RunHistory], None] | None = None,
        deadline: float | None = None,
    ) -> RunHistory:
        repo, clock = self.repository, self.repository.clock
        run_id = history.manifest.id
        deadline = (
            deadline
            if deadline is not None
            else clock.monotonic() + history.manifest.settings.deadline_seconds
        )
        queue = [
            (clock.monotonic() + item.delay_seconds, item)
            for item in history.work(retry_unknown=segment.retry_unknown)
        ]
        active: dict[asyncio.Task[DispatchOutcome], AttemptRecord] = {}
        stop = Stop()
        outer_cancelled = False
        try:
            while queue or active:
                if stop.persistence_failed or stop.unsettled_contention:
                    break
                try:
                    current = await self._source_call(
                        run_id, "history", lambda: repo.history(run_id)
                    )
                except _SourceContentionExhausted as error:
                    self._record_contention(stop, error)
                    break
                for task in tuple(active):
                    if not task.done():
                        continue
                    attempt = active.pop(task)
                    outcome = task.result()
                    if outcome.retryable and stop.state is None:
                        retry = next(
                            (
                                work
                                for work in current.work()
                                if work.prepared.case_id == attempt.case_id
                                and work.kind == "rate_retry"
                            ),
                            None,
                        )
                        if retry is not None:
                            queue.append((clock.monotonic() + retry.delay_seconds, retry))
                    if progress is not None:
                        try:
                            progress(current)
                        except Exception:
                            stop.state = "interrupted"
                            stop.reason = ServiceError(
                                code="internal_error", reason="progress_callback_failed"
                            )
                try:
                    cancel_requested = await self._source_call(
                        run_id,
                        "cancel_observation",
                        lambda current=current: repo.cancelled(current, segment),
                    )
                except _SourceContentionExhausted as error:
                    self._record_contention(stop, error)
                    break
                if cancel_requested:
                    stop.state = "cancelled"
                    stop.reason = ServiceError(code="run_incomplete", reason="cancel_requested")
                elif clock.monotonic() >= deadline and queue:
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(code="run_incomplete", reason="segment_deadline")
                elif current.remaining <= 0 and queue:
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(
                        code="run_incomplete",
                        reason="execution_group_cap"
                        if current.group and current.group.remaining == 0
                        else "attempt_cap",
                    )
                if stop.state is None:
                    queue.sort(key=lambda entry: entry[0])
                    while (
                        queue
                        and queue[0][0] <= clock.monotonic()
                        and len(active) < history.manifest.settings.concurrency
                    ):
                        due_at, work = queue.pop(0)
                        try:
                            reserved = await self._source_call(
                                run_id,
                                "reservation",
                                lambda work=work: repo.reserve(
                                    run_id, segment, work, deadline=deadline
                                ),
                                deadline=deadline,
                            )
                        except _SegmentDeadlineElapsed:
                            queue.insert(0, (due_at, work))
                            stop.state = "budget_exhausted"
                            stop.reason = ServiceError(
                                code="run_incomplete", reason="segment_deadline"
                            )
                            break
                        except _SourceContentionExhausted as error:
                            queue.insert(0, (due_at, work))
                            self._record_contention(stop, error)
                            break
                        if reserved is None:
                            queue.insert(0, (due_at, work))
                            break
                        self.hook("after_intent", reserved)
                        task = asyncio.create_task(
                            self._dispatch(
                                reserved,
                                segment,
                                backend,
                                stop,
                                history.manifest.settings.timeout_seconds,
                                deadline,
                            )
                        )
                        active[task] = reserved
                if stop.state is not None and not active:
                    break
                if not active and not queue:
                    break
                await self.waiter.wait(0.05)
        except asyncio.CancelledError:
            outer_cancelled = True
            stop.state = "interrupted"
            stop.reason = ServiceError(code="run_incomplete", reason="owner_cancelled")
        except _SourceContentionExhausted as error:
            self._record_contention(stop, error)
        except ServiceFailure:
            stop.persistence_failed = True
            stop.state = "interrupted"
            stop.reason = ServiceError(code="internal_error", reason="persistence_failed")
        finally:
            if active:
                # Parent task cancellation never abandons transport cleanup or drops
                # execution ownership while a child is still using the provider.
                settled = asyncio.gather(*active, return_exceptions=True)
                while not settled.done():
                    try:
                        await asyncio.shield(settled)
                    except asyncio.CancelledError:
                        outer_cancelled = True
                        stop.state = "interrupted"
        if stop.persistence_failed:
            raise ServiceFailure(
                ServiceError(code="internal_error", resource_id=run_id, reason="persistence_failed")
            ) from None
        if stop.unsettled_contention:
            assert stop.contention_failure is not None
            raise ServiceFailure(stop.contention_failure) from None

        def finalize() -> RunHistory:
            current = repo.history(run_id)
            cancel_requested = repo.cancelled(current, segment)
            if cancel_requested and not outer_cancelled:
                stop.state = "cancelled"
                stop.reason = ServiceError(
                    code="run_incomplete", reason="cancel_requested", resource_id=run_id
                )
            elif stop.state is None:
                if clock.monotonic() >= deadline and any(
                    item.status == "pending" for item in current.results()
                ):
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(
                        code="run_incomplete", reason="segment_deadline", resource_id=run_id
                    )
                elif queue and current.remaining <= 0:
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(
                        code="run_incomplete",
                        resource_id=run_id,
                        reason=(
                            "execution_group_cap"
                            if current.group and current.group.remaining == 0
                            else "attempt_cap"
                        ),
                    )
            state = stop.state or (
                "completed"
                if all(item.status == "valid" for item in current.results())
                else "completed_with_errors"
            )
            return repo.finish(run_id, state, segment.id, stop.reason)

        try:
            result = await self._source_call(run_id, "finalization", finalize)
        except _SourceContentionExhausted as error:
            self._record_contention(stop, error)
            raise ServiceFailure(error.error) from None
        except ServiceFailure:
            raise ServiceFailure(
                ServiceError(code="internal_error", resource_id=run_id, reason="persistence_failed")
            ) from None
        if stop.contention_failure is not None:
            raise ServiceFailure(stop.contention_failure) from None
        if outer_cancelled:
            raise asyncio.CancelledError
        return result
