"""Bounded async scheduling; durable intent precedes every single transport call."""

import asyncio
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import partial
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
_SOURCE_GATE: ContextVar[asyncio.Lock | None] = ContextVar("experiment_source_gate", default=None)


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


@dataclass
class ProviderStop:
    failed: bool = False
    reason: ServiceError | None = None


@dataclass
class ConcurrencyShare:
    limit: int
    changed: asyncio.Event = field(default_factory=asyncio.Event)

    def add(self, slots: int) -> None:
        self.limit += slots
        self.changed.set()


def _observe_provider_stop(stop: Stop, shared: ProviderStop | None) -> None:
    if shared is not None and shared.failed and stop.state is None:
        stop.state = "interrupted"
        stop.reason = shared.reason or ServiceError(
            code="run_incomplete", reason="provider_wide_failure"
        )


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
        for value in item.values():
            if isinstance(value, str):
                value.encode("utf-8", "strict")
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
        self._default_hook: Callable[[str, AttemptRecord], None] = lambda _stage, _attempt: None
        self.hook = hook or self._default_hook

    @staticmethod
    def _cap_reason(history: RunHistory) -> str:
        group = history.group
        if group is not None:
            if group.remaining == 0:
                return "execution_group_cap"
            if group.group.kind == "experiment" and group.remaining_for(history.manifest.id) == 0:
                return "experiment_reservation_budget"
        return "attempt_cap"

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
        offload: bool = False,
        source_gate: asyncio.Lock | None = None,
    ) -> _RepositoryResult:
        """Retry only source-lock acquisition, never a callable that entered its epoch."""
        gate = source_gate if source_gate is not None else _SOURCE_GATE.get()
        if gate is not None:
            async with gate:
                token = _SOURCE_GATE.set(None)
                try:
                    return await self._source_call(
                        run_id, stage, operation, deadline=deadline, offload=offload
                    )
                finally:
                    _SOURCE_GATE.reset(token)
        repo = self.repository
        budget_deadline = repo.clock.monotonic() + _SOURCE_CONTENTION_BUDGET_SECONDS
        delay_index = 0
        priority_index = 0
        while True:
            now = repo.clock.monotonic()
            if deadline is not None and now >= deadline and deadline <= budget_deadline:
                raise _SegmentDeadlineElapsed
            if delay_index and now >= budget_deadline:
                raise _SourceContentionExhausted(run_id, stage)
            if deadline is not None and now >= deadline:
                raise _SegmentDeadlineElapsed
            entered = False

            def invoke() -> _RepositoryResult:
                nonlocal entered
                with repo.source.consistent_read():
                    entered = True
                    return operation()

            try:
                if not offload:
                    return invoke()
                pending = asyncio.create_task(asyncio.to_thread(invoke))
                try:
                    return await asyncio.shield(pending)
                except asyncio.CancelledError:
                    # Source publication must finish before execution ownership is released.
                    while not pending.done():
                        try:
                            await asyncio.shield(pending)
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            break
                    if not pending.cancelled():
                        pending.exception()
                    raise
            except ServiceFailure as error:
                if (
                    entered
                    or error.error.code != "conflict"
                    or error.error.reason not in {"source_busy", "source_priority"}
                ):
                    raise
                now = repo.clock.monotonic()
                if deadline is not None and now >= deadline:
                    raise _SegmentDeadlineElapsed from None
                if error.error.reason == "source_priority":
                    delay = _SOURCE_CONTENTION_DELAYS_SECONDS[
                        min(priority_index, len(_SOURCE_CONTENTION_DELAYS_SECONDS) - 1)
                    ]
                    if deadline is not None:
                        delay = min(delay, deadline - now)
                    await self.waiter.wait(delay)
                    budget_deadline += max(0.0, repo.clock.monotonic() - now)
                    priority_index += 1
                    continue
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
        *,
        dispatch_ready: bool | None = None,
        received: list[tuple[AttemptRecord, DispatchOutcome, float | None]] | None = None,
        provider_stop: ProviderStop | None = None,
    ) -> DispatchOutcome:
        repo = self.repository
        started: float | None = None
        duration: float | None = None
        outcome: DispatchOutcome
        cancelled = False
        try:
            _observe_provider_stop(stop, provider_stop)
            if stop.state is not None:
                outcome = DispatchOutcome(
                    state="not_sent",
                    error=ServiceError(code="run_incomplete", reason="cancelled_before_dispatch"),
                )
            else:
                try:
                    dispatched = dispatch_ready
                    if dispatched and repo.clock.monotonic() >= deadline:
                        dispatched = False
                    if dispatched is None:
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
                    _observe_provider_stop(stop, provider_stop)
                    if stop.state is not None:
                        dispatched = False
                    if not dispatched:
                        if repo.clock.monotonic() >= deadline:
                            stop.state = "budget_exhausted"
                            stop.reason = ServiceError(
                                code="run_incomplete",
                                resource_id=attempt.run_id,
                                reason="segment_deadline",
                            )
                        outcome = DispatchOutcome(
                            state="not_sent",
                            error=stop.reason
                            if stop.state == "budget_exhausted"
                            else ServiceError(
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
            if provider_stop is not None:
                provider_stop.failed = True
                provider_stop.reason = outcome.error
        settlement_duration = (
            duration
            if duration is not None
            else max(0.0, repo.clock.monotonic() - started)
            if started is not None
            else None
        )
        if received is not None:
            received.append((attempt, outcome, settlement_duration))
            if cancelled:
                raise asyncio.CancelledError
            return outcome
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
        concurrency_override: int | None = None,
        source_gate: asyncio.Lock | None = None,
        provider_stop: ProviderStop | None = None,
        concurrency_share: ConcurrencyShare | None = None,
    ) -> RunHistory:
        if source_gate is not None:
            token = _SOURCE_GATE.set(source_gate)
            try:
                return await self.run(
                    history,
                    segment,
                    backend,
                    progress=progress,
                    deadline=deadline,
                    concurrency_override=concurrency_override,
                    provider_stop=provider_stop,
                    concurrency_share=concurrency_share,
                )
            finally:
                _SOURCE_GATE.reset(token)
        concurrency = history.manifest.settings.concurrency
        if concurrency_override is not None:
            if not 1 <= concurrency_override <= concurrency:
                raise ValueError("invalid_concurrency_override")
            concurrency = concurrency_override
        if len(history.prepared) >= 64 and self.hook is self._default_hook:
            return await self._run_bulk(
                history,
                segment,
                backend,
                progress=progress,
                deadline=deadline,
                concurrency=concurrency,
                provider_stop=provider_stop,
                concurrency_share=concurrency_share,
            )
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
                if concurrency_share is not None:
                    concurrency = concurrency_share.limit
                _observe_provider_stop(stop, provider_stop)
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
                        partial(repo.cancelled, current, segment),
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
                        reason=self._cap_reason(current),
                    )
                _observe_provider_stop(stop, provider_stop)
                if stop.state is None:
                    queue.sort(key=lambda entry: entry[0])
                    while queue and queue[0][0] <= clock.monotonic() and len(active) < concurrency:
                        due_at, work = queue.pop(0)
                        try:
                            reserved = await self._source_call(
                                run_id,
                                "reservation",
                                partial(repo.reserve, run_id, segment, work, deadline=deadline),
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
                                provider_stop=provider_stop,
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
                        reason=self._cap_reason(current),
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

    async def _run_bulk(
        self,
        history: RunHistory,
        segment: RunSegment,
        backend: Backend,
        *,
        progress: Callable[[RunHistory], None] | None,
        deadline: float | None,
        concurrency: int,
        provider_stop: ProviderStop | None,
        concurrency_share: ConcurrencyShare | None,
    ) -> RunHistory:
        repo, clock = self.repository, self.repository.clock
        source_call = partial(self._source_call, offload=True)
        run_id = history.manifest.id
        deadline = (
            deadline
            if deadline is not None
            else (clock.monotonic() + history.manifest.settings.deadline_seconds)
        )
        queue = [
            (clock.monotonic() + work.delay_seconds, work)
            for work in history.work(retry_unknown=segment.retry_unknown)
        ]
        active: dict[asyncio.Task[DispatchOutcome], AttemptRecord] = {}
        received: list[tuple[AttemptRecord, DispatchOutcome, float | None]] = []
        stop = Stop()
        outer_cancelled = False

        async def settle() -> tuple[RunHistory, bool]:
            batch = tuple(received)

            def capture() -> tuple[RunHistory, bool]:
                if batch:
                    repo.settle_many(batch)
                current = repo.history(run_id)
                return current, repo.cancelled(current, segment)

            try:
                return await source_call(run_id, "settlement" if batch else "history", capture)
            finally:
                # Uncertain publications never replay; later responses are separate work.
                del received[: len(batch)]

        try:
            while queue or active:
                if concurrency_share is not None:
                    concurrency_share.changed.clear()
                    concurrency = concurrency_share.limit
                _observe_provider_stop(stop, provider_stop)
                if stop.persistence_failed:
                    break
                had_received = bool(received)
                settled = tuple(received)
                current, cancel_requested = await settle()
                settled_ids = {attempt.id for attempt, _, _ in settled}
                for task, attempt in tuple(active.items()):
                    if task.done() and attempt.id in settled_ids:
                        del active[task]
                        task.result()
                if settled and stop.state is None:
                    eligible = {work.prepared.case_id: work for work in current.work()}
                    for attempt, outcome, _ in settled:
                        retry = eligible.get(attempt.case_id)
                        if outcome.retryable and retry is not None and retry.kind == "rate_retry":
                            queue.append((clock.monotonic() + retry.delay_seconds, retry))
                if had_received and progress is not None:
                    try:
                        progress(current)
                    except Exception:
                        stop.state = "interrupted"
                        stop.reason = ServiceError(
                            code="internal_error", reason="progress_callback_failed"
                        )
                if cancel_requested:
                    stop.state = "cancelled"
                    stop.reason = ServiceError(code="run_incomplete", reason="cancel_requested")
                elif queue and (clock.monotonic() >= deadline or current.remaining <= 0):
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(
                        code="run_incomplete",
                        reason=(
                            "segment_deadline"
                            if clock.monotonic() >= deadline
                            else self._cap_reason(current)
                        ),
                    )
                _observe_provider_stop(stop, provider_stop)
                if stop.state is None:
                    queue.sort(key=lambda entry: entry[0])
                    available = concurrency - len(active)
                    due = tuple(
                        work for due_at, work in queue[:available] if due_at <= clock.monotonic()
                    )
                    if due:
                        try:
                            prepared = await source_call(
                                run_id,
                                "reservation",
                                partial(
                                    repo.prepare_dispatch_many,
                                    run_id,
                                    segment,
                                    due,
                                    deadline=deadline,
                                ),
                                deadline=deadline,
                            )
                        except _SegmentDeadlineElapsed:
                            stop.state = "budget_exhausted"
                            stop.reason = ServiceError(
                                code="run_incomplete", reason="segment_deadline"
                            )
                        else:
                            del queue[: len(prepared)]
                            for attempt, ready in prepared:
                                task = asyncio.create_task(
                                    self._dispatch(
                                        attempt,
                                        segment,
                                        backend,
                                        stop,
                                        history.manifest.settings.timeout_seconds,
                                        deadline,
                                        dispatch_ready=ready,
                                        received=received,
                                        provider_stop=provider_stop,
                                    )
                                )
                                active[task] = attempt
                if not active and (not queue or stop.state is not None):
                    break
                if received:
                    continue
                pending = [task for task in active if not task.done()]
                if pending:
                    delay = None
                    if stop.state is None and queue and len(active) < concurrency:
                        delay = max(0.0, min(due_at for due_at, _ in queue) - clock.monotonic())
                    watchers: list[asyncio.Task[object]] = []
                    if delay is not None:
                        watchers.append(asyncio.create_task(self.waiter.wait(delay)))
                    if concurrency_share is not None:
                        watchers.append(asyncio.create_task(concurrency_share.changed.wait()))
                    try:
                        await asyncio.wait(
                            [*pending, *watchers], return_when=asyncio.FIRST_COMPLETED
                        )
                    finally:
                        for watcher in watchers:
                            watcher.cancel()
                        await asyncio.gather(*watchers, return_exceptions=True)
                elif queue:
                    delay = max(0.0, min(due_at for due_at, _ in queue) - clock.monotonic())
                    await self.waiter.wait(min(0.25, delay))
        except asyncio.CancelledError:
            outer_cancelled = True
            stop.state = "interrupted"
            stop.reason = ServiceError(code="run_incomplete", reason="owner_cancelled")
        except _SourceContentionExhausted as error:
            self._record_contention(stop, error)
        except ServiceFailure:
            stop.persistence_failed = True
        finally:
            if active:
                drained = asyncio.gather(*active, return_exceptions=True)
                while not drained.done():
                    try:
                        await asyncio.shield(drained)
                    except asyncio.CancelledError:
                        outer_cancelled = True
                        stop.state = "interrupted"
                        stop.reason = ServiceError(code="run_incomplete", reason="owner_cancelled")
            # Received responses remain unknown after any failed publication; never redispatch.
            if received:
                try:
                    current, cancel_requested = await settle()
                except _SourceContentionExhausted as error:
                    self._record_contention(stop, error)
                except ServiceFailure:
                    stop.persistence_failed = True
        if stop.persistence_failed:
            raise ServiceFailure(
                ServiceError(code="internal_error", resource_id=run_id, reason="persistence_failed")
            ) from None
        if stop.contention_failure is not None:
            raise ServiceFailure(stop.contention_failure)

        def finalize() -> RunHistory:
            current = repo.history(run_id)
            if repo.cancelled(current, segment) and not outer_cancelled:
                stop.state = "cancelled"
                stop.reason = ServiceError(code="run_incomplete", reason="cancel_requested")
            elif (
                stop.state is None
                and clock.monotonic() >= deadline
                and any(item.status == "pending" for item in current.results())
            ):
                stop.state = "budget_exhausted"
                stop.reason = ServiceError(code="run_incomplete", reason="segment_deadline")
            state = stop.state or (
                "completed"
                if all(item.status == "valid" for item in current.results())
                else "completed_with_errors"
            )
            return repo.finish(run_id, state, segment.id, stop.reason)

        try:
            result = await source_call(run_id, "finalization", finalize)
        except _SourceContentionExhausted as error:
            raise ServiceFailure(error.error) from None
        except ServiceFailure:
            raise ServiceFailure(
                ServiceError(code="internal_error", resource_id=run_id, reason="persistence_failed")
            ) from None
        if outer_cancelled:
            raise asyncio.CancelledError
        return result
