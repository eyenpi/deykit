"""One execution owner around logical starts/resumes and their settled async work."""

from collections.abc import Callable

from deykit.application.dataset_support import fail, identifier, page, safe_hash
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import new_id
from deykit.contracts.ports import Clock, CommitReceipt, SnapshotSource
from deykit.contracts.records import AttemptRecord, RunSegment
from deykit.runner.history import RunHistory
from deykit.runner.planner import Planner, RunRequest, start_intent, validate_request
from deykit.runner.ports import Backend, BackendFactory, ExecutionProject, Waiter
from deykit.runner.repository import RunRepository
from deykit.runner.scheduler import Scheduler
from deykit.runner.views import (
    ResumePreview,
    RunCreated,
    RunPage,
    RunPreview,
    RunProgress,
    RunResumed,
    preview_view,
    progress_view,
)


class ExecutionService:
    def __init__(
        self,
        source: SnapshotSource,
        execution: ExecutionProject,
        backends: BackendFactory,
        clock: Clock,
        id_factory: Callable[[], str] = new_id,
        *,
        waiter: Waiter | None = None,
        hook: Callable[[str, AttemptRecord], None] | None = None,
    ) -> None:
        self.source, self.execution, self.backends = source, execution, backends
        self.planner = Planner(source, backends)
        self.repository = RunRepository(source, execution, clock, id_factory)
        self.scheduler = Scheduler(self.repository, waiter=waiter, hook=hook)

    def preview(self, request: RunRequest) -> RunPreview:
        return preview_view(self.planner.prepare(request))

    def _backend(self, history: RunHistory) -> Backend:
        profile = history.manifest.provider
        if profile is None:
            fail("missing_frozen_provider", "incompatible_data")
        backend = self.backends.resolve(profile, history.manifest.fixture_set_id)
        problem = backend.preflight(
            history.manifest.decision_id or "", history.manifest.dataset_id or ""
        )
        if problem:
            fail(problem.reason or "provider_preflight_failed", "preflight_failed")
        return backend

    def _created(
        self, history: RunHistory, replayed: bool, callback: Callable[[RunCreated], None] | None
    ) -> None:
        if callback is None:
            return
        try:
            callback(RunCreated(history.manifest.id, history.manifest.mode, replayed))
        except Exception:
            if not replayed:
                try:
                    self.repository.finish(
                        history.manifest.id,
                        "interrupted",
                        reason=ServiceError(
                            code="internal_error",
                            resource_id=history.manifest.id,
                            reason="created_callback_failed",
                        ),
                    )
                except ServiceFailure as failure:
                    raise ServiceFailure(
                        failure.error.model_copy(update={"resource_id": history.manifest.id})
                    ) from None
                except Exception:
                    raise ServiceFailure(
                        ServiceError(
                            code="internal_error",
                            resource_id=history.manifest.id,
                            reason="created_callback_finish_failed",
                        )
                    ) from None
            raise ServiceFailure(
                ServiceError(
                    code="internal_error",
                    resource_id=history.manifest.id,
                    reason="created_callback_failed",
                )
            ) from None

    def _receipt(self, operation_id: str, digest: str) -> CommitReceipt | None:
        # A receipt read is the sole pre-ownership source boundary. It cannot dispatch.
        with self.source.consistent_read():
            return self.source.operation_receipt(operation_id, intent_hash=digest)

    @staticmethod
    def _require_start_ready(history: RunHistory) -> RunSegment:
        run_id = history.manifest.id
        first = tuple(
            segment
            for segment in history.segments
            if segment.run_id == run_id and segment.sequence == 1
        )
        if len(first) != 1:
            raise ServiceFailure(
                ServiceError(
                    code="run_incomplete",
                    resource_id=run_id,
                    reason="start_acknowledgement_incomplete",
                )
            )
        segment = first[0]
        if not any(
            event.run_id == run_id
            and event.segment_id == segment.id
            and event.state == "segment_ready"
            for event in history.events
        ):
            raise ServiceFailure(
                ServiceError(
                    code="run_incomplete",
                    resource_id=run_id,
                    reason="start_acknowledgement_incomplete",
                )
            )
        return segment

    def _capture_start_ready(self, operation_id: str, digest: str) -> RunHistory | None:
        """Capture one original receipt and its durably admitted first segment."""
        with self.source.consistent_read():
            receipt = self.source.operation_receipt(operation_id, intent_hash=digest)
            if receipt is None:
                return None
            run_id = self.repository.replay_run(receipt)
            history = self.repository.history(run_id)
            self._require_start_ready(history)
            return history

    def _start_replay(
        self, receipt: CommitReceipt, callback: Callable[[RunCreated], None] | None
    ) -> RunProgress:
        history = self.repository.history(self.repository.replay_run(receipt))
        self._created(history, True, callback)
        return progress_view(history, replayed=True, active=self.execution.execution_active())

    async def start(
        self,
        request: RunRequest,
        *,
        operation_id: str,
        on_created: Callable[[RunCreated], None] | None = None,
        on_progress: Callable[[RunProgress], None] | None = None,
        expected_review_context_hash: str | None = None,
    ) -> RunProgress:
        request, operation_id = validate_request(request), identifier(operation_id)
        digest = start_intent(request, expected_review_context_hash)
        if on_created is None:
            receipt = self._receipt(operation_id, digest)
            if receipt is not None:
                return self._start_replay(receipt, None)
        else:
            history = self._capture_start_ready(operation_id, digest)
            if history is not None:
                active = self.execution.execution_active()
                self._created(history, True, on_created)
                return progress_view(history, replayed=True, active=active)
        try:
            return await self._start_owned(
                request,
                operation_id=operation_id,
                on_created=on_created,
                on_progress=on_progress,
                expected_review_context_hash=expected_review_context_hash,
            )
        except ServiceFailure as failure:
            if failure.error.code == "execution_locked":
                if on_created is None:
                    receipt = self._receipt(operation_id, digest)
                    if receipt is not None:
                        return self._start_replay(receipt, None)
                else:
                    history = self._capture_start_ready(operation_id, digest)
                    if history is not None:
                        active = self.execution.execution_active()
                        self._created(history, True, on_created)
                        return progress_view(history, replayed=True, active=active)
            raise

    async def _start_owned(
        self,
        request: RunRequest,
        *,
        operation_id: str,
        on_created: Callable[[RunCreated], None] | None = None,
        on_progress: Callable[[RunProgress], None] | None = None,
        expected_review_context_hash: str | None = None,
    ) -> RunProgress:
        request, operation_id = validate_request(request), identifier(operation_id)
        digest = start_intent(request, expected_review_context_hash)
        with self.execution.execution_owner():
            replay_history: RunHistory | None = None
            if on_created is None:
                with self.source.consistent_read():
                    replay = self.source.operation_receipt(operation_id, intent_hash=digest)
                if replay is not None:
                    replay_history = self.repository.history(self.repository.replay_run(replay))
            else:
                replay_history = self._capture_start_ready(operation_id, digest)
            if replay_history is not None:
                history = replay_history
                self._created(history, True, on_created)
                return progress_view(history, replayed=True)
            plan = self.planner.prepare(request)
            replay_history = None
            replayed = False
            with self.source.consistent_read():
                if on_created is None:
                    replay = self.source.operation_receipt(operation_id, intent_hash=digest)
                    if replay is not None:
                        run_id = self.repository.replay_run(replay)
                        replayed = True
                    else:
                        run_id = None
                else:
                    replay_history = self._capture_start_ready(operation_id, digest)
                    run_id = replay_history.manifest.id if replay_history is not None else None
                if run_id is None:
                    self.planner.check_context(plan)
                    from deykit.runner.review import require_review_hash, run_review_hash

                    require_review_hash(expected_review_context_hash, run_review_hash(plan))
                    run_id = self.repository.freeze(plan, operation_id, digest)
            if replay_history is not None:
                self._created(replay_history, True, on_created)
                return progress_view(replay_history, replayed=True)
            if replayed:
                history = self.repository.history(run_id)
                return progress_view(history, replayed=True)
            if on_created is None:
                history = self.repository.history(run_id)
                segment = self.repository.segment(
                    run_id,
                    self.repository.identity(),
                    safe_hash({"command": "run.first_segment", "run_id": run_id}),
                    acknowledge_cancellation=False,
                )
            else:
                try:
                    segment = self.repository.segment(
                        run_id,
                        self.repository.identity(),
                        safe_hash({"command": "run.first_segment", "run_id": run_id}),
                        acknowledge_cancellation=False,
                    )
                except ServiceFailure as failure:
                    if (
                        failure.error.code != "internal_error"
                        or failure.error.reason != "storage_io"
                    ):
                        raise
                    raise ServiceFailure(
                        ServiceError(
                            code="run_incomplete",
                            resource_id=run_id,
                            reason="start_acknowledgement_incomplete",
                        )
                    ) from None
                except OSError:
                    raise ServiceFailure(
                        ServiceError(
                            code="run_incomplete",
                            resource_id=run_id,
                            reason="start_acknowledgement_incomplete",
                        )
                    ) from None
                captured = self._capture_start_ready(operation_id, digest)
                if captured is None or captured.manifest.id != run_id:
                    raise ServiceFailure(
                        ServiceError(
                            code="run_incomplete",
                            resource_id=run_id,
                            reason="start_acknowledgement_incomplete",
                        )
                    )
                history = captured
                self._created(history, False, on_created)
            result = await self.scheduler.run(
                self.repository.history(run_id),
                segment.record,
                self._backend(history),
                deadline=segment.monotonic_deadline,
                progress=(lambda current: on_progress(progress_view(current, active=True)))
                if on_progress
                else None,
            )
            return progress_view(result)

    def show(self, run_id: str) -> RunProgress:
        identifier(run_id)
        if self.execution.execution_active():
            return progress_view(self.repository.history(run_id), active=True)
        try:
            with self.execution.execution_owner():
                return progress_view(self.repository.recover(run_id))
        except ServiceFailure as error:
            if error.error.code == "execution_locked":
                return progress_view(self.repository.history(run_id), active=True)
            raise

    def list(
        self,
        *,
        decision_id: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> RunPage:
        if decision_id is not None:
            identifier(decision_id)
        with self.source.consistent_read():
            ids = self.source.list_ids("runs")
        views = tuple(self.show(run_id) for run_id in ids)
        filtered = {
            view.run_id: view
            for view in views
            if (decision_id is None or view.decision_id == decision_id)
            and (status is None or view.state == status)
        }
        chosen, next_cursor = page(tuple(filtered), cursor, limit)
        return RunPage(tuple(filtered[key] for key in chosen), len(filtered), next_cursor)

    def cancel(self, run_id: str, *, operation_id: str) -> RunProgress:
        return progress_view(
            self.repository.cancel(run_id, operation_id), active=self.execution.execution_active()
        )

    @staticmethod
    def _resume_cap(history: RunHistory, total: int | None) -> int:
        if history.manifest.execution_group_id:
            raise ServiceFailure(
                ServiceError(
                    code="preflight_failed",
                    resource_id=history.manifest.execution_group_id,
                    reason="resume_execution_group_required",
                )
            )
        if total is None:
            return history.cap
        if type(total) is not int or total < max(history.cap, history.used):
            fail("invalid_cap_extension", "preflight_failed")
        return total

    def preview_resume(
        self, run_id: str, *, retry_unknown: bool = False, max_attempts: int | None = None
    ) -> ResumePreview:
        if type(retry_unknown) is not bool:
            fail("invalid_unknown_retry_choice")
        history = self.repository.history(run_id)
        self._backend(history)
        return ResumePreview(
            progress_view(history, active=self.execution.execution_active()),
            tuple(work.prepared.case_id for work in history.work(retry_unknown=retry_unknown)),
            retry_unknown,
            self._resume_cap(history, max_attempts),
        )

    def _resumed(
        self,
        history: RunHistory,
        segment_id: str,
        replayed: bool,
        callback: Callable[[RunResumed], None] | None,
    ) -> None:
        if callback is None:
            return
        try:
            callback(RunResumed(history.manifest.id, segment_id, history.manifest.mode, replayed))
        except Exception:
            if not replayed:
                self.repository.finish(
                    history.manifest.id,
                    "interrupted",
                    segment_id,
                    ServiceError(code="internal_error", reason="resumed_callback_failed"),
                )
            fail("resumed_callback_failed", "internal_error")

    def _resume_replay(
        self, receipt: CommitReceipt, callback: Callable[[RunResumed], None] | None
    ) -> RunProgress:
        history = self.repository.history(self.repository.replay_run(receipt))
        segment_id = next(
            (item.key.resource_id for item in receipt.changes if item.key.collection == "segments"),
            None,
        )
        if segment_id is None:
            fail("incomplete_resume_receipt", "internal_error")
        if not any(
            event.state == "segment_ready" and event.segment_id == segment_id
            for event in history.events
        ):
            if not self.execution.execution_active():
                self.show(history.manifest.id)  # Safe recovery; never acknowledges cancellations.
            raise ServiceFailure(
                ServiceError(
                    code="run_incomplete",
                    resource_id=history.manifest.id,
                    reason="resume_acknowledgement_incomplete",
                )
            )
        self._resumed(history, segment_id, True, callback)
        return progress_view(history, replayed=True, active=self.execution.execution_active())

    @staticmethod
    def _resume_intent(run_id: str, retry_unknown: bool, max_attempts: int | None) -> str:
        identifier(run_id)
        if type(retry_unknown) is not bool:
            fail("invalid_unknown_retry_choice")
        if max_attempts is not None and type(max_attempts) is not int:
            fail("invalid_cap_extension")
        return safe_hash(
            {
                "command": "run.resume",
                "run_id": run_id,
                "retry_unknown": retry_unknown,
                "max_attempts": max_attempts,
            }
        )

    async def resume(
        self,
        run_id: str,
        *,
        operation_id: str,
        retry_unknown: bool = False,
        max_attempts: int | None = None,
        on_resumed: Callable[[RunResumed], None] | None = None,
        on_progress: Callable[[RunProgress], None] | None = None,
    ) -> RunProgress:
        identifier(operation_id)
        digest = self._resume_intent(run_id, retry_unknown, max_attempts)
        receipt = self._receipt(operation_id, digest)
        if receipt is not None:
            return self._resume_replay(receipt, on_resumed)
        try:
            return await self._resume_owned(
                run_id,
                operation_id=operation_id,
                retry_unknown=retry_unknown,
                max_attempts=max_attempts,
                on_resumed=on_resumed,
                on_progress=on_progress,
            )
        except ServiceFailure as failure:
            if failure.error.code == "execution_locked":
                receipt = self._receipt(operation_id, digest)
                if receipt is not None:
                    return self._resume_replay(receipt, on_resumed)
            raise

    async def _resume_owned(
        self,
        run_id: str,
        *,
        operation_id: str,
        retry_unknown: bool = False,
        max_attempts: int | None = None,
        on_progress: Callable[[RunProgress], None] | None = None,
        on_resumed: Callable[[RunResumed], None] | None = None,
    ) -> RunProgress:
        identifier(run_id)
        identifier(operation_id)
        if type(retry_unknown) is not bool:
            fail("invalid_unknown_retry_choice")
        if max_attempts is not None and type(max_attempts) is not int:
            fail("invalid_cap_extension")
        digest = safe_hash(
            {
                "command": "run.resume",
                "run_id": run_id,
                "retry_unknown": retry_unknown,
                "max_attempts": max_attempts,
            }
        )
        with self.execution.execution_owner():
            with self.source.consistent_read():
                replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self._resume_replay(replay, on_resumed)
            with self.source.consistent_read():
                self._resume_cap(self.repository.history(run_id), max_attempts)
                history = self.repository.recover(run_id)
                self._resume_cap(history, max_attempts)
                if any(
                    event.outcome and event.outcome.provider_wide
                    for event in history.attempt_events
                ):
                    fail("terminal_provider_failure_requires_new_run", "preflight_failed")
            backend = self._backend(history)
            segment = self.repository.segment(
                run_id, operation_id, digest, retry_unknown=retry_unknown, max_attempts=max_attempts
            )
            self._resumed(self.repository.history(run_id), segment.record.id, False, on_resumed)
            result = await self.scheduler.run(
                self.repository.history(run_id),
                segment.record,
                backend,
                deadline=segment.monotonic_deadline,
                progress=(lambda current: on_progress(progress_view(current, active=True)))
                if on_progress
                else None,
            )
            return progress_view(result)
