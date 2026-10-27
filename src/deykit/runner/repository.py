"""Short atomic source transactions for run snapshots, controls and attempt lifecycle."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from deykit.application.dataset_support import decoded, fail, identifier, safe_hash
from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import GROUP_SELECTION_LIMITS, JsonError, bytes_hash, dump_json
from deykit.contracts.ports import (
    Clock,
    Collection,
    CommitReceipt,
    IncrementalRecordViewSource,
    RecordViewSource,
    ResourceKey,
    SnapshotSource,
    SourceChange,
)
from deykit.contracts.records import (
    AttemptEvent,
    AttemptRecord,
    CaseResult,
    DatasetSnapshot,
    DecisionRevision,
    DispatchOutcome,
    LabelSnapshot,
    PreparedCase,
    ResultSnapshot,
    RunControl,
    RunEvent,
    RunManifest,
    RunSegment,
)
from deykit.runner._history_index import HistoryIndex
from deykit.runner.decoding import HistoryDecoder
from deykit.runner.history import RunHistory, WorkItem, history_from_records, read_history
from deykit.runner.planner import MAX_PLAN_BYTES, RunPlan, evidence_hash
from deykit.runner.ports import ExecutionProject
from deykit.runner.result_limits import (
    experiment_case_result_limit,
    experiment_nonanswer_result_limit,
    result_size,
)

RunState = Literal[
    "preparing",
    "running",
    "cancelling",
    "cancelled",
    "completed",
    "completed_with_errors",
    "budget_exhausted",
    "interrupted",
    "preflight_failed",
    "attempt_reserved",
    "attempt_dispatched",
    "attempt_settled",
    "cap_extended",
    "segment_ready",
]


def change(collection: Collection, record: Record, scope: tuple[str, ...] = ()) -> SourceChange:
    try:
        return SourceChange(
            ResourceKey(collection, str(getattr(record, "id", None)), scope),
            dump_record(record),
            None,
        )
    except JsonError as error:
        fail(error.code, "preflight_failed")


def deadline_at(start: str, seconds: int) -> str:
    try:
        return (
            (datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(seconds=seconds))
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (ValueError, OverflowError):
        fail("invalid_segment_deadline", "preflight_failed")


@dataclass(frozen=True)
class StartedSegment:
    record: RunSegment
    monotonic_deadline: float


class RunRepository:
    def __init__(
        self,
        source: SnapshotSource,
        execution: ExecutionProject,
        clock: Clock,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.source, self.execution, self.clock, self.id_factory = (
            source,
            execution,
            clock,
            id_factory,
        )

        self._decoder = HistoryDecoder()
        self._history_index = HistoryIndex(self._decoder)

    @property
    def decoder(self) -> HistoryDecoder:
        return self._decoder

    def identity(self) -> str:
        return identifier(self.id_factory())

    def history(self, run_id: str) -> RunHistory:
        run_id = identifier(run_id)
        if callable(getattr(self.source, "read_record_view", None)):
            view = cast(IncrementalRecordViewSource, self.source).read_record_view(
                self._history_index.vector
            )
            return self._history_index.capture(view.records, run_id, view=view)
        if callable(getattr(self.source, "read_records", None)):
            records = cast(RecordViewSource, self.source).read_records()
            return self._history_index.capture(records, run_id)
        return read_history(self.source, run_id, decoder=self._decoder)

    @staticmethod
    def replay_run(receipt: CommitReceipt) -> str:
        stored = next(
            (record for record in receipt.changes if record.key.collection == "runs"), None
        )
        if stored is None:
            # Resume/cancel receipts have run-scoped operational records.
            scoped = next(
                (
                    record
                    for record in receipt.changes
                    if record.key.collection in {"segments", "run_controls"}
                ),
                None,
            )
            if scoped is None:
                fail("incomplete_run_receipt", "internal_error")
            return scoped.key.scope[0]
        return decoded(RunManifest, stored).id

    def event(
        self,
        history: RunHistory,
        state: RunState,
        *,
        segment_id: str | None = None,
        attempt_id: str | None = None,
        reason: ServiceError | None = None,
    ) -> RunEvent:
        return RunEvent(
            id=self.identity(),
            run_id=history.manifest.id,
            segment_id=segment_id,
            attempt_id=attempt_id,
            sequence=history.boundary + 1,
            state=state,
            created_at=self.clock.utc_now(),
            reason=reason,
        )

    def freeze(self, plan: RunPlan, operation_id: str, intent_hash: str) -> str:
        """Caller holds the short source lock after checking the captured context."""
        run_id = self.identity()
        changes = self.stage_freeze(plan, operation_id, run_id=run_id)
        self.source.commit(operation_id, changes, intent_hash=intent_hash)
        return run_id

    def stage_freeze(
        self,
        plan: RunPlan,
        operation_id: str,
        *,
        run_id: str,
        group_id: str | None = None,
        max_plan_bytes: int | None = None,
    ) -> tuple[SourceChange, ...]:
        """Build immutable evidence without writing, for an atomic multi-plan freeze."""
        revision_id, dataset_id, label_id, dev_id, dev_label_id = (
            self.identity() for _ in range(5)
        )
        stamp = self.clock.utc_now()
        revision = DecisionRevision(
            id=revision_id,
            decision_id=plan.selection.decision_id,
            definition=plan.definition,
            content_hash=plan.definition_hash,
            created_at=stamp,
            note="run_snapshot",
        )
        dataset = DatasetSnapshot(
            id=dataset_id,
            dataset_id=plan.selection.dataset_id,
            cases=plan.cases,
            content_hash=evidence_hash(tuple(dump_record(case) for case in plan.cases)),
            created_at=stamp,
            selection_source=dump_json(
                {"split": plan.selection.split, "case_ids": list(plan.selection.case_ids)},
                limits=GROUP_SELECTION_LIMITS,
            ),
        )
        labels = LabelSnapshot(
            id=label_id,
            decision_id=plan.selection.decision_id,
            dataset_snapshot_id=dataset_id,
            labels=plan.labels,
            content_hash=evidence_hash(tuple(dump_record(label) for label in plan.labels)),
            created_at=stamp,
        )
        development = DatasetSnapshot(
            id=dev_id,
            dataset_id=plan.selection.dataset_id,
            cases=plan.development_cases,
            content_hash=evidence_hash(tuple(dump_record(case) for case in plan.development_cases)),
            created_at=stamp,
            selection_source='{"split":"development","scope":"full_dataset"}',
        )
        dev_labels = LabelSnapshot(
            id=dev_label_id,
            decision_id=plan.selection.decision_id,
            dataset_snapshot_id=dev_id,
            labels=plan.development_labels,
            content_hash=evidence_hash(
                tuple(dump_record(label) for label in plan.development_labels)
            ),
            created_at=stamp,
        )
        manifest = RunManifest(
            id=run_id,
            execution_group_id=group_id,
            regression_ids=plan.selection.regression_ids,
            baseline_unavailable_reason=(
                "frozen_regression_selection" if plan.selection.regression_ids else None
            ),
            decision_id=plan.selection.decision_id,
            dataset_id=plan.selection.dataset_id,
            decision_revision_id=revision_id,
            dataset_snapshot_id=dataset_id,
            label_snapshot_id=label_id,
            baseline_dataset_snapshot_id=dev_id,
            baseline_label_snapshot_id=dev_label_id,
            option_order=plan.selection.option_order,
            provider_profile_id=plan.provider.id,
            provider_config_hash=bytes_hash(dump_record(plan.provider)),
            provider=plan.provider,
            fixture_set_id=plan.selection.fixture_set_id,
            adapter=plan.provider.adapter,
            compiler_version=next(
                (item.request.compiler_version for item in plan.prepared if item.request),
                "not_compiled",
            ),
            requested_model=plan.provider.requested_model,
            mode=plan.selection.mode,
            case_ids=tuple(case.id for case in plan.cases),
            settings=plan.selection.settings,
            created_at=stamp,
            operation_id=operation_id,
        )
        prepared = tuple(
            PreparedCase(
                id=item.case_id,
                run_id=run_id,
                case_id=item.case_id,
                input_hash=item.input_hash,
                request=item.request,
                error=item.error,
            )
            for item in plan.prepared
        )
        event = RunEvent(
            id=self.identity(), run_id=run_id, sequence=1, state="preparing", created_at=stamp
        )
        history = RunHistory(manifest, prepared, (), (event,), (), (), (), ())
        initial_snapshot = self.snapshot_record(history)
        limit = MAX_PLAN_BYTES if max_plan_bytes is None else max_plan_bytes
        changes: list[SourceChange] = []
        size = 0

        def append(collection: Collection, record: Record, scope: tuple[str, ...] = ()) -> None:
            nonlocal size
            staged = change(collection, record, scope)
            size += len(staged.body or b"")
            if size > limit:
                fail("run_resource_limit", "preflight_failed")
            changes.append(staged)

        append("revisions", revision, (plan.selection.decision_id,))
        append("dataset_snapshots", dataset)
        append("label_snapshots", labels)
        append("dataset_snapshots", development)
        append("label_snapshots", dev_labels)
        append("runs", manifest)
        for item in prepared:
            append("prepared_cases", item, (run_id,))
        append("run_events", event, (run_id,))
        append("result_snapshots", initial_snapshot)
        return tuple(changes)

    def segment(
        self,
        run_id: str,
        operation_id: str,
        intent_hash: str,
        *,
        retry_unknown: bool = False,
        max_attempts: int | None = None,
        acknowledge_cancellation: bool = True,
    ) -> StartedSegment:
        with self.source.consistent_read():
            history = self.history(run_id)
            if history.manifest.execution_group_id:
                fail("resume_execution_group_required", "preflight_failed")
            changes: list[SourceChange] = []
            through = len(history.controls)
            if max_attempts is not None:
                if type(max_attempts) is not int or max_attempts < max(history.cap, history.used):
                    fail("invalid_cap_extension", "preflight_failed")
                if max_attempts > history.cap:
                    through += 1
                    control = RunControl(
                        id=self.identity(),
                        run_id=run_id,
                        sequence=through,
                        operation_id=operation_id,
                        action="cap_extension",
                        max_attempts=max_attempts,
                        created_at=self.clock.utc_now(),
                    )
                    changes.append(change("run_controls", control, (run_id,)))
            stamp = self.clock.utc_now()
            deadline = self.clock.monotonic() + history.manifest.settings.deadline_seconds
            segment = RunSegment(
                id=self.identity(),
                run_id=run_id,
                started_at=stamp,
                deadline_at=deadline_at(stamp, history.manifest.settings.deadline_seconds),
                retry_unknown=retry_unknown,
                sequence=len(history.segments) + 1,
                cancel_through_sequence=through if acknowledge_cancellation else 0,
            )
            event = self.event(history, "running", segment_id=segment.id)
            changes.extend(
                (change("segments", segment, (run_id,)), change("run_events", event, (run_id,)))
            )
            self.source.commit(operation_id, tuple(changes), intent_hash=intent_hash)
            # Existing storage flags are acknowledged before any dispatch. A failure
            # here leaves a durable segment but never starts work; explicit resume recovers.
            if acknowledge_cancellation:
                self.execution.acknowledge_cancel(run_id, segment.id)
            # The segment receipt alone is not an acknowledgement: legacy storage
            # acknowledgement can fail after that commit. Persist its completed boundary.
            ready = self.event(self.history(run_id), "segment_ready", segment_id=segment.id)
            self.source.commit(self.identity(), (change("run_events", ready, (run_id,)),))
            return StartedSegment(segment, deadline)

    def cancelled(self, history: RunHistory, segment: RunSegment) -> bool:
        def requested(member: RunHistory, cutoff: RunSegment) -> bool:
            return any(
                control.action == "cancel" and control.sequence > cutoff.cancel_through_sequence
                for control in member.controls
            ) or self.execution.cancellation_requested(member.manifest.id)

        if history.group and history.group.segments:
            with self.source.consistent_read():
                records = self.source.capture_snapshot()
                # Preserve the caller segment's acknowledgement epoch, never a newer one.
                group_segment = next(
                    (
                        s
                        for s in history.group.segments
                        if any(
                            m.run_id == history.manifest.id and m.segment_id == segment.id
                            for m in s.member_segments
                        )
                    ),
                    None,
                )
                if group_segment is None:
                    fail("unowned_group_child_segment", "incompatible_data")
                for linked in group_segment.member_segments:
                    member = history_from_records(
                        records, linked.run_id, verify_group=False, decoder=self.decoder
                    )
                    cutoff = next(s for s in member.segments if s.id == linked.segment_id)
                    if requested(member, cutoff):
                        return True
            return False
        return requested(history, segment)

    def cancel(self, run_id: str, operation_id: str) -> RunHistory:
        identifier(run_id)
        identifier(operation_id)
        digest = safe_hash({"command": "run.cancel", "run_id": run_id})
        with self.source.consistent_read():
            replay = self.source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return self.history(self.replay_run(replay))
            history = self.history(run_id)
            control = RunControl(
                id=self.identity(),
                run_id=run_id,
                sequence=len(history.controls) + 1,
                operation_id=operation_id,
                action="cancel",
                created_at=self.clock.utc_now(),
            )
            event = self.event(
                history,
                "cancelling",
                segment_id=history.segments[-1].id if history.segments else None,
            )
            self.source.commit(
                operation_id,
                (change("run_controls", control, (run_id,)),)
                + (
                    (change("run_events", event, (run_id,)),)
                    if history.state in {"preparing", "running", "cancelling"}
                    else ()
                ),
                intent_hash=digest,
            )
            return self.history(run_id)

    def reserve(
        self, run_id: str, segment: RunSegment, work: WorkItem, *, deadline: float
    ) -> AttemptRecord | None:
        prepared = self._prepare_many(run_id, segment, (work,), deadline=deadline, dispatch=False)
        return prepared[0][0] if prepared else None

    def _prepare_many(
        self,
        run_id: str,
        segment: RunSegment,
        work: tuple[WorkItem, ...],
        *,
        deadline: float,
        dispatch: bool,
    ) -> tuple[tuple[AttemptRecord, bool], ...]:
        if not work:
            return ()
        with self.source.consistent_read():
            history = self.history(run_id)
            if history.group:
                latest = history.group.segments[-1] if history.group.segments else None
                if (
                    latest is None
                    or not any(
                        item.run_id == run_id and item.segment_id == segment.id
                        for item in latest.member_segments
                    )
                    or not any(
                        event.state == "segment_ready" and event.segment_id == segment.id
                        for event in history.events
                    )
                ):
                    fail("execution_group_not_ready", "run_incomplete")
            if (
                history.remaining <= 0
                or self.clock.monotonic() >= deadline
                or self.cancelled(history, segment)
            ):
                return ()
            eligible = {
                item.prepared.case_id: item
                for item in history.work(retry_unknown=segment.retry_unknown)
            }
            attempts: list[tuple[AttemptRecord, bool]] = []
            changes: list[SourceChange] = []
            selected: set[str] = set()
            sequence = history.boundary
            for item in work[: history.remaining]:
                if self.clock.monotonic() >= deadline:
                    break
                current = eligible.get(item.prepared.case_id)
                if current is None or current != item or item.prepared.case_id in selected:
                    fail("run_work_changed", "conflict")
                selected.add(item.prepared.case_id)
                if item.prepared.request is None:
                    fail("invalid_dispatch_plan", "internal_error")
                attempt = AttemptRecord(
                    id=self.identity(),
                    run_id=run_id,
                    segment_id=segment.id,
                    case_id=item.prepared.case_id,
                    number=history.used + len(attempts) + 1,
                    request=item.prepared.request,
                    reserved_at=self.clock.utc_now(),
                    kind=item.kind,
                    prior_attempt_id=item.prior_attempt_id,
                )
                reserved = AttemptEvent(
                    id=self.identity(),
                    attempt_id=attempt.id,
                    sequence=1,
                    state="reserved",
                    created_at=self.clock.utc_now(),
                )
                sequence += 1
                run_event = self.event(
                    history, "attempt_reserved", segment_id=segment.id, attempt_id=attempt.id
                ).model_copy(update={"sequence": sequence})
                changes.extend(
                    (
                        change("attempts", attempt, (run_id,)),
                        change("attempt_events", reserved, (attempt.id,)),
                        change("run_events", run_event, (run_id,)),
                    )
                )
                ready = dispatch and self.clock.monotonic() < deadline
                if ready:
                    sequence += 1
                    dispatched = AttemptEvent(
                        id=self.identity(),
                        attempt_id=attempt.id,
                        sequence=2,
                        state="dispatched",
                        created_at=self.clock.utc_now(),
                    )
                    dispatched_run = self.event(
                        history, "attempt_dispatched", segment_id=segment.id, attempt_id=attempt.id
                    ).model_copy(update={"sequence": sequence})
                    changes.extend(
                        (
                            change("attempt_events", dispatched, (attempt.id,)),
                            change("run_events", dispatched_run, (run_id,)),
                        )
                    )
                attempts.append((attempt, ready))
                if dispatch and not ready:
                    break
            if changes:
                self.source.commit(self.identity(), tuple(changes))
            return tuple(attempts)

    def dispatched(self, attempt: AttemptRecord, segment: RunSegment, *, deadline: float) -> bool:
        with self.source.consistent_read():
            history = self.history(attempt.run_id)
            if self.cancelled(history, segment) or self.clock.monotonic() >= deadline:
                return False
            prior = history.final_event(attempt.id)
            if prior is None or prior.state != "reserved":
                fail("invalid_attempt_transition", "conflict")
            event = AttemptEvent(
                id=self.identity(),
                attempt_id=attempt.id,
                sequence=prior.sequence + 1,
                state="dispatched",
                created_at=self.clock.utc_now(),
            )
            run_event = self.event(
                history, "attempt_dispatched", segment_id=attempt.segment_id, attempt_id=attempt.id
            )
            self.source.commit(
                self.identity(),
                (
                    change("attempt_events", event, (attempt.id,)),
                    change("run_events", run_event, (attempt.run_id,)),
                ),
            )
            return True

    def settle(
        self,
        attempt: AttemptRecord,
        outcome: DispatchOutcome,
        *,
        duration_seconds: float | None = None,
    ) -> None:
        self.settle_many(((attempt, outcome, duration_seconds),))

    def prepare_dispatch_many(
        self, run_id: str, segment: RunSegment, work: tuple[WorkItem, ...], *, deadline: float
    ) -> tuple[tuple[AttemptRecord, bool], ...]:
        return self._prepare_many(run_id, segment, work, deadline=deadline, dispatch=True)

    def settle_many(
        self, received: tuple[tuple[AttemptRecord, DispatchOutcome, float | None], ...]
    ) -> None:
        if not received:
            return
        run_id = received[0][0].run_id
        with self.source.consistent_read():
            history = self.history(run_id)
            changes: list[SourceChange] = []
            settled: set[str] = set()
            prepared = {item.case_id: item for item in history.prepared}
            experiment = history.group is not None and history.group.group.kind == "experiment"
            answer_limit = (
                experiment_case_result_limit(
                    len(history.prepared),
                    min(
                        history.manifest.settings.max_attempts,
                        sum(item.request is not None for item in history.prepared),
                    ),
                )
                if experiment
                else 0
            )
            nonanswer_limit = (
                experiment_nonanswer_result_limit(len(history.prepared)) if experiment else 0
            )
            for index, (attempt, outcome, duration) in enumerate(received, 1):
                prior = history.final_event(attempt.id)
                if (
                    attempt.run_id != run_id
                    or attempt.id in settled
                    or prior is None
                    or prior.state not in {"reserved", "dispatched"}
                ):
                    fail("invalid_attempt_transition", "conflict")
                settled.add(attempt.id)
                if experiment:
                    if outcome.answer is not None:
                        result = CaseResult(
                            case_id=attempt.case_id,
                            input_hash=prepared[attempt.case_id].input_hash,
                            status="valid",
                            attempt_id=attempt.id,
                            answer=outcome.answer,
                        )
                        limit = answer_limit
                    else:
                        result = CaseResult(
                            case_id=attempt.case_id,
                            input_hash=prepared[attempt.case_id].input_hash,
                            status="unknown" if outcome.state == "unknown" else "response_error",
                            attempt_id=attempt.id,
                            error=outcome.error,
                        )
                        limit = nonanswer_limit
                    if result_size(result) > limit:
                        outcome = outcome.model_copy(
                            update={
                                "answer": None,
                                "retryable": False,
                                "retry_after_seconds": None,
                                "error": ServiceError(
                                    code="response_invalid",
                                    reason="experiment_result_resource_limit",
                                ),
                            }
                        )
                event = AttemptEvent(
                    id=self.identity(),
                    attempt_id=attempt.id,
                    sequence=prior.sequence + 1,
                    state=outcome.state,
                    outcome=outcome,
                    duration_seconds=duration,
                    created_at=self.clock.utc_now(),
                )
                run_event = self.event(
                    history, "attempt_settled", segment_id=attempt.segment_id, attempt_id=attempt.id
                ).model_copy(update={"sequence": history.boundary + index})
                changes.extend(
                    (
                        change("attempt_events", event, (attempt.id,)),
                        change("run_events", run_event, (run_id,)),
                    )
                )
            self.source.commit(self.identity(), tuple(changes))

    def recover(self, run_id: str) -> RunHistory:
        """Only an OS execution owner may call recovery; never sends requests."""
        with self.source.consistent_read():
            history = self.history(run_id)
            interrupted = False
            for attempt in history.attempts:
                prior = history.final_event(attempt.id)
                if prior is not None and prior.state in {"reserved", "dispatched"}:
                    interrupted = True
                    self.settle(
                        attempt,
                        DispatchOutcome(
                            state="unknown",
                            error=ServiceError(code="run_incomplete", reason="owner_interrupted"),
                        ),
                    )
            if interrupted or history.state in {"preparing", "running", "cancelling"}:
                self.finish(
                    run_id, "interrupted", history.segments[-1].id if history.segments else None
                )
            return self.history(run_id)

    def snapshot_record(self, history: RunHistory) -> ResultSnapshot:
        results = history.results()
        # CaseResult is an owned typed envelope; user input remains absent here.
        digest = evidence_hash(tuple(item.model_dump_json().encode("utf-8") for item in results))
        return ResultSnapshot(
            id=self.identity(),
            run_id=history.manifest.id,
            results=results,
            through_event_sequence=history.boundary,
            content_hash=digest,
            created_at=self.clock.utc_now(),
        )

    def finish(
        self,
        run_id: str,
        state: RunState,
        segment_id: str | None = None,
        reason: ServiceError | None = None,
    ) -> RunHistory:
        with self.source.consistent_read():
            history = self.history(run_id)
            event = self.event(history, state, segment_id=segment_id, reason=reason)
            updated = RunHistory(
                history.manifest,
                history.prepared,
                history.segments,
                (*history.events, event),
                history.attempts,
                history.attempt_events,
                history.controls,
                history.snapshots,
            )
            snapshot = self.snapshot_record(updated)
            self.source.commit(
                self.identity(),
                (change("run_events", event, (run_id,)), change("result_snapshots", snapshot)),
            )
            return self.history(run_id)
