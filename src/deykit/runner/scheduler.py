"""Bounded async scheduling; durable intent precedes every single transport call."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import AttemptRecord, DispatchOutcome, NormalizedAnswer, RunSegment
from deykit.runner.history import RunHistory
from deykit.runner.ports import Backend, Waiter
from deykit.runner.repository import RunRepository, RunState


class AsyncWaiter:
    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass
class Stop:
    state: RunState | None = None
    reason: ServiceError | None = None
    persistence_failed: bool = False


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
            if stop.state is not None or not repo.dispatched(attempt, segment, deadline=deadline):
                outcome = DispatchOutcome(
                    state="not_sent",
                    error=ServiceError(code="run_incomplete", reason="cancelled_before_dispatch"),
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
        try:
            repo.settle(
                attempt,
                outcome,
                duration_seconds=duration
                if duration is not None
                else (max(0.0, repo.clock.monotonic() - started) if started is not None else None),
            )
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
                if stop.persistence_failed:
                    break
                current = repo.history(run_id)
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
                if repo.cancelled(current, segment):
                    stop.state = "cancelled"
                    stop.reason = ServiceError(code="run_incomplete", reason="cancel_requested")
                elif clock.monotonic() >= deadline and queue:
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(code="run_incomplete", reason="segment_deadline")
                elif current.used >= current.cap and queue:
                    stop.state = "budget_exhausted"
                    stop.reason = ServiceError(code="run_incomplete", reason="attempt_cap")
                if stop.state is None:
                    queue.sort(key=lambda entry: entry[0])
                    while (
                        queue
                        and queue[0][0] <= clock.monotonic()
                        and len(active) < history.manifest.settings.concurrency
                    ):
                        _, work = queue.pop(0)
                        reserved = repo.reserve(run_id, segment, work, deadline=deadline)
                        if reserved is None:
                            queue.insert(0, (clock.monotonic(), work))
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
                if not active and (stop.state is not None or not queue):
                    break
                await self.waiter.wait(0.05)
        except asyncio.CancelledError:
            outer_cancelled = True
            stop.state = "interrupted"
            stop.reason = ServiceError(code="run_incomplete", reason="owner_cancelled")
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
        current = repo.history(run_id)
        if (
            stop.state is None
            and clock.monotonic() >= deadline
            and any(result.status == "pending" for result in current.results())
        ):
            stop.state = "budget_exhausted"
            stop.reason = ServiceError(code="run_incomplete", reason="segment_deadline")
        state = stop.state or (
            "completed"
            if all(result.status == "valid" for result in current.results())
            else "completed_with_errors"
        )
        result = repo.finish(run_id, state, segment.id, stop.reason)
        if outer_cancelled:
            raise asyncio.CancelledError
        return result
