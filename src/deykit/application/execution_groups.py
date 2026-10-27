"""Atomic group freezing and explicit recovery using the existing run scheduler."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal, NoReturn, cast

from deykit.application.dataset_support import decoded, fail, identifier, safe_hash
from deykit.application.errors import ServiceFailure
from deykit.application.execution import ExecutionService
from deykit.contracts.errors import ServiceError
from deykit.contracts.execution_groups import (
    ExecutionGroup,
    ExecutionGroupSegment,
    GroupMemberSegment,
)
from deykit.contracts.json_value import JsonSource, bytes_hash
from deykit.contracts.ports import (
    CommitReceipt,
    CreateTransactionPreviewSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import RunSegment
from deykit.runner.decoding import HistoryDecoder
from deykit.runner.group_evidence import admit_group_snapshots, group_budget
from deykit.runner.group_models import (
    GroupAcknowledged,
    GroupKind,
    GroupMemberResumePreview,
    GroupPlan,
    GroupPreview,
    GroupProgress,
    GroupResumePreview,
    MemberIdentity,
    request_identity,
)
from deykit.runner.group_repository import GroupRepository
from deykit.runner.group_selection import (
    decode_group_start_selection,
    encode_group_start_selection,
    group_start_intent,
)
from deykit.runner.history import RunHistory, history_from_records
from deykit.runner.planner import MAX_EXPERIMENT_PLAN_BYTES, MAX_PLAN_BYTES
from deykit.runner.ports import Backend
from deykit.runner.review import (
    _record_identities,
    group_review_hash,
    regression_membership_records,
    require_review_hash,
)
from deykit.runner.views import preview_view, progress_view


@dataclass(frozen=True)
class _AdmittedAcknowledgement:
    group: ExecutionGroup
    segment: ExecutionGroupSegment
    progress: GroupProgress
    event: GroupAcknowledged


GroupAcknowledgementCallback = Callable[[GroupAcknowledged], None | Awaitable[None]]


class GroupExecutionService:
    """One owner, one source epoch per preflight, and one lifetime budget per group.

    The supplied preparation callback is application composition, not a transport:
    it must return locally compiled plans and is never called for an operation replay.
    """

    def __init__(self, execution: ExecutionService) -> None:
        self.runner = execution
        self.source = execution.source
        self.repo = execution.repository
        self.store = GroupRepository(self.repo)

    def preview(self, prepare: Callable[[], GroupPlan], *, selection_source: str) -> GroupPreview:
        plan = prepare()
        plan.validate()
        review_context_hash = group_review_hash(plan, selection_source)
        selection = encode_group_start_selection(
            selection_source, expected_review_context_hash=review_context_hash
        )
        # Include the reviewed selection envelope and same initial segment/readiness footprints.
        digest = group_start_intent(selection)
        group, changes = self.store.stage_freeze(plan, "preview", digest, selection.stored_source)
        records = self._staged(changes)
        segment, segment_changes = self.store.stage_segment(
            group, "preview", 1, False, records, initial=True
        )
        ready_changes = self.store.stage_ready(segment, self._staged((*changes, *segment_changes)))
        self._check_size((*changes, *segment_changes, *ready_changes), kind=plan.kind)
        if plan.kind == "experiment" and isinstance(self.source, CreateTransactionPreviewSource):
            self.source.preview_create_transaction((*changes, *segment_changes))
        return GroupPreview(
            plan.kind,
            tuple(preview_view(p) for p in plan.plans),
            sum(p.initial_requests for p in plan.plans),
            plan.max_attempts,
            plan.deadline_seconds,
            review_context_hash,
            identities=tuple(
                MemberIdentity(
                    p.selection.option_order,
                    tuple(request_identity(c.case_id, c.input_hash, c.request) for c in p.prepared),
                )
                for p in plan.plans
            ),
            independent_case_count=len(
                {(p.selection.dataset_id, c.id) for p in plan.plans for c in p.cases}
            ),
        )

    @staticmethod
    def _seed(group: ExecutionGroup) -> int | None:
        if group.kind != "choice_order":
            return None
        selection = decode_group_start_selection(
            group.selection_source, expected_kind=group.kind
        ).original_selection
        if type(selection) is not dict or type(selection.get("request")) is not dict:
            fail("invalid_group_selection", "incompatible_data")
        request = selection["request"]
        assert isinstance(request, dict)
        seed = request.get("seed")
        if (
            not isinstance(seed, (int, Decimal))
            or isinstance(seed, bool)
            or seed != int(seed)
            or not -(2**63) <= seed < 2**63
        ):
            fail("invalid_group_seed", "incompatible_data")
        return int(seed)

    @staticmethod
    def _staged(changes: tuple[SourceChange, ...]) -> tuple[StoredRecord, ...]:
        return tuple(
            StoredRecord(c.key, c.body, bytes_hash(c.body)) for c in changes if c.body is not None
        )

    @staticmethod
    def _check_size(changes: tuple[SourceChange, ...], *, kind: GroupKind = "choice_order") -> None:
        limit = MAX_EXPERIMENT_PLAN_BYTES if kind == "experiment" else MAX_PLAN_BYTES
        if sum(len(c.body or b"") for c in changes) > limit:
            fail("execution_group_resource_limit", "preflight_failed")

    def _check_selection(self, plan: GroupPlan) -> None:
        if plan.kind != "regression_check":
            return
        captured = self.source.capture_snapshot()
        explicit_ids = (
            None
            if plan.default_regression_ids is not None
            else tuple(
                record.key.resource_id
                for record in plan.review_membership_records
                if record.key.collection == "regressions"
            )
        )
        try:
            current = regression_membership_records(
                captured, plan.plans[0].selection.decision_id, explicit_ids
            )
        except ServiceFailure:
            fail("run_source_changed", "conflict")
        if _record_identities(current) != _record_identities(plan.review_membership_records):
            fail("run_source_changed", "conflict")

    def _receipt(self, operation_id: str, digest: str) -> CommitReceipt | None:
        with self.source.consistent_read():
            return self.source.operation_receipt(operation_id, intent_hash=digest)

    @staticmethod
    def _require_kind(group: ExecutionGroup, expected_kind: GroupKind | None) -> None:
        if expected_kind is None:
            return
        if expected_kind not in ("choice_order", "regression_check", "experiment"):
            fail("invalid_execution_group_kind")
        if group.kind != expected_kind:
            fail(
                "diagnostic_group_required"
                if expected_kind == "choice_order"
                else "regression_check_group_required"
                if expected_kind == "regression_check"
                else "experiment_group_required"
            )

    @staticmethod
    def _validate_expected_kind(expected_kind: GroupKind | None) -> None:
        if expected_kind is not None and expected_kind not in (
            "choice_order",
            "regression_check",
            "experiment",
        ):
            fail("invalid_execution_group_kind")

    @staticmethod
    def _acknowledgement_incomplete(group_id: str | None) -> NoReturn:
        raise ServiceFailure(
            ServiceError(
                code="run_incomplete",
                reason="group_acknowledgement_incomplete",
                resource_id=group_id,
            )
        ) from None

    def _admit_acknowledgement(
        self,
        records: tuple[StoredRecord, ...],
        receipt: CommitReceipt,
        *,
        command: Literal["start", "resume"],
        digest: str,
        requested_group_id: str | None = None,
        expected_kind: GroupKind | None = None,
        retry_unknown: bool | None = None,
        active: bool = False,
        replayed: bool,
    ) -> _AdmittedAcknowledgement:
        if receipt.deleted_keys or len({r.key for r in receipt.changes}) != len(receipt.changes):
            fail("invalid_group_receipt", "incompatible_data")
        if not receipt.operation_id:
            self._acknowledgement_incomplete(requested_group_id)
        groups = tuple(r for r in receipt.changes if r.key.collection == "execution_groups")
        segments = tuple(r for r in receipt.changes if r.key.collection == "group_segments")
        if command == "start":
            if len(groups) != 1 or len(segments) != 1:
                self._acknowledgement_incomplete(requested_group_id)
            group_record = decoded(ExecutionGroup, groups[0])
            group_id = group_record.id
            segment_record = segments[0]
        else:
            if groups or len(segments) != 1:
                self._acknowledgement_incomplete(requested_group_id)
            segment_record = segments[0]
            segment_hint = decoded(ExecutionGroupSegment, segment_record)
            group_id = segment_hint.group_id
            group_record = None

        if requested_group_id is not None and group_id != requested_group_id:
            fail("conflict", "conflict")
        segment = decoded(ExecutionGroupSegment, segment_record)
        if segment.group_id != group_id or segment.operation_id != receipt.operation_id:
            fail("invalid_group_receipt", "incompatible_data")
        if command == "start":
            if (
                group_record is None
                or group_record.operation_id != receipt.operation_id
                or group_record.intent_hash != digest
                or segment.sequence != 1
                or segment.retry_unknown
            ):
                fail("invalid_group_receipt", "incompatible_data")
        elif retry_unknown is None or segment.retry_unknown != retry_unknown:
            fail("invalid_group_receipt", "incompatible_data")

        index = {record.key: record for record in records}
        captured_group = index.get(ResourceKey("execution_groups", group_id))
        captured_segment = index.get(ResourceKey("group_segments", segment.id, (group_id,)))
        if (
            captured_group is None
            or captured_segment is None
            or (group_record is not None and captured_group != groups[0])
            or captured_segment != segment_record
        ):
            fail("invalid_group_receipt", "incompatible_data")

        budget = group_budget(records, group_id, decoder=self.repo.decoder)
        self._require_kind(budget.group, expected_kind)
        admit_group_snapshots(records, group_id, decoder=self.repo.decoder)
        admitted_segment = next((item for item in budget.segments if item.id == segment.id), None)
        if admitted_segment != segment:
            fail("invalid_group_receipt", "incompatible_data")
        if command == "resume" and requested_group_id != group_id:
            fail("conflict", "conflict")

        histories = tuple(
            history_from_records(
                records, member.run_id, verify_group=False, decoder=self.repo.decoder
            )
            for member in budget.group.members
        )
        if len(segment.member_segments) != len(budget.group.members):
            fail("invalid_group_receipt", "incompatible_data")
        modes = tuple(history.manifest.mode for history in histories)
        if not modes or any(mode != modes[0] for mode in modes):
            fail("execution_group_mode_mismatch", "incompatible_data")
        for expected_member, linked_member, history in zip(
            budget.group.members, segment.member_segments, histories, strict=True
        ):
            if linked_member.run_id != expected_member.run_id or not any(
                event.state == "segment_ready" and event.segment_id == linked_member.segment_id
                for event in history.events
            ):
                self._acknowledgement_incomplete(group_id)

        progress = self.captured_progress(records, group_id, active=active, replayed=replayed)
        event = GroupAcknowledged(
            group_id=group_id,
            kind=budget.group.kind,
            mode=modes[0],
            segment_id=segment.id,
            replayed=replayed,
            member_run_ids=tuple(member.run_id for member in budget.group.members),
        )
        return _AdmittedAcknowledgement(budget.group, segment, progress, event)

    def _capture_acknowledgement(
        self,
        operation_id: str,
        digest: str,
        *,
        command: Literal["start", "resume"],
        requested_group_id: str | None = None,
        expected_kind: GroupKind | None = None,
        retry_unknown: bool | None = None,
        replayed: bool,
        active: bool | None = None,
    ) -> _AdmittedAcknowledgement | None:
        with self.source.consistent_read():
            receipt = self.source.operation_receipt(operation_id, intent_hash=digest)
            if receipt is None:
                return None
            if receipt.operation_id != operation_id:
                fail("invalid_group_receipt", "incompatible_data")
            records = self.source.capture_snapshot()
            admitted = self._admit_acknowledgement(
                records,
                receipt,
                command=command,
                digest=digest,
                requested_group_id=requested_group_id,
                expected_kind=expected_kind,
                retry_unknown=retry_unknown,
                active=False,
                replayed=replayed,
            )
        # Ownership status is observational and must not precede receipt/graph admission.
        if active is None:
            active = self.runner.execution.execution_active()
        return replace(
            admitted,
            progress=self.captured_progress(
                records, admitted.group.id, active=active, replayed=replayed
            ),
        )

    def _admit_resume_receipt_kind(
        self,
        receipt: CommitReceipt,
        *,
        operation_id: str,
        group_id: str,
        retry_unknown: bool,
        expected_kind: GroupKind | None,
    ) -> None:
        if receipt.operation_id != operation_id:
            fail("invalid_group_receipt", "incompatible_data")
        if receipt.deleted_keys or len({r.key for r in receipt.changes}) != len(receipt.changes):
            fail("invalid_group_receipt", "incompatible_data")
        segments = tuple(r for r in receipt.changes if r.key.collection == "group_segments")
        if len(segments) != 1 or any(
            record.key.collection == "execution_groups" for record in receipt.changes
        ):
            fail("invalid_group_receipt", "incompatible_data")
        segment_record = decoded(ExecutionGroupSegment, segments[0])
        if (
            segment_record.group_id != group_id
            or segment_record.operation_id != operation_id
            or segment_record.retry_unknown != retry_unknown
        ):
            fail("conflict", "conflict")
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
            budget = group_budget(records, group_id, decoder=self.repo.decoder)
            self._require_kind(budget.group, expected_kind)
            if not any(item == segment_record for item in budget.segments):
                fail("invalid_group_receipt", "incompatible_data")

    @staticmethod
    async def _notify_acknowledged(
        callback: GroupAcknowledgementCallback | None,
        value: _AdmittedAcknowledgement,
        *,
        reason: str,
    ) -> None:
        if callback is None:
            return
        try:
            result = callback(value.event)
            if result is not None:
                await result
        except Exception:
            raise ServiceFailure(
                ServiceError(code="internal_error", reason=reason, resource_id=value.group.id)
            ) from None

    def _observe_owned_acknowledgement(
        self, value: _AdmittedAcknowledgement
    ) -> _AdmittedAcknowledgement:
        # Probe ownership only after admission and outside the source epoch.
        active = self.runner.execution.execution_active()
        members = tuple(
            replace(
                member,
                execution_active=active and member.state in {"preparing", "running", "cancelling"},
            )
            for member in value.progress.members
        )
        return replace(value, progress=replace(value.progress, members=members))

    def _backend_captured(self, history: RunHistory, records: tuple[StoredRecord, ...]) -> Backend:
        profile = history.manifest.provider
        if profile is None:
            fail("missing_frozen_provider", "incompatible_data")
        backend = self.runner.backends.resolve_captured(
            profile, history.manifest.fixture_set_id, records
        )
        problem = backend.preflight(
            history.manifest.decision_id or "", history.manifest.dataset_id or ""
        )
        if problem:
            fail(problem.reason or "provider_preflight_failed", "preflight_failed")
        return backend

    @staticmethod
    def _receipt_group_id(receipt: CommitReceipt) -> str | None:
        group_record = next(
            (record for record in receipt.changes if record.key.collection == "execution_groups"),
            None,
        )
        if group_record is not None:
            return decoded(ExecutionGroup, group_record).id
        segment_record = next(
            (record for record in receipt.changes if record.key.collection == "group_segments"),
            None,
        )
        return decoded(ExecutionGroupSegment, segment_record).group_id if segment_record else None

    def _replay(self, receipt: CommitReceipt) -> GroupProgress:
        record = next((r for r in receipt.changes if r.key.collection == "execution_groups"), None)
        if record:
            group_id = decoded(ExecutionGroup, record).id
        else:
            record = next(
                (r for r in receipt.changes if r.key.collection == "group_segments"), None
            )
            if record is None:
                fail("incomplete_group_receipt", "internal_error")
            group_id = decoded(ExecutionGroupSegment, record).group_id
        return self.show(group_id, replayed=True)

    def show(self, group_id: str, *, replayed: bool = False) -> GroupProgress:
        identifier(group_id)
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
        budget = group_budget(records, group_id, decoder=self.repo.decoder)
        selected = admit_group_snapshots(records, group_id, decoder=self.repo.decoder)
        active = self.runner.execution.execution_active()
        unsettled = any(
            history_from_records(
                records, m.run_id, verify_group=False, decoder=self.repo.decoder
            ).state
            in {"running", "preparing", "cancelling"}
            for m in budget.group.members
        )
        missing = bool(budget.segments) and not any(
            s.segment_id == budget.segments[-1].id for s in selected
        )
        if not active and (unsettled or missing):
            try:
                with self.runner.execution.execution_owner():
                    # Recapture and admit the complete graph under actual ownership BEFORE repairs.
                    with self.source.consistent_read():
                        records = self.source.capture_snapshot()
                        budget = group_budget(records, group_id, decoder=self.repo.decoder)
                        admit_group_snapshots(records, group_id, decoder=self.repo.decoder)
                        for member in budget.group.members:
                            self.repo.recover(member.run_id)
                        if budget.segments:
                            self.store.snapshot(budget.group, budget.segments[-1])
                        records = self.source.capture_snapshot()
                        budget = group_budget(records, group_id, decoder=self.repo.decoder)
                        selected = admit_group_snapshots(
                            records, group_id, decoder=self.repo.decoder
                        )
            except ServiceFailure as failure:
                if failure.error.code != "execution_locked":
                    raise
                active = True
        return self.captured_progress(
            records, group_id, active=active, replayed=replayed, decoder=self.repo.decoder
        )

    @staticmethod
    def captured_progress(
        records: tuple[StoredRecord, ...],
        group_id: str,
        *,
        active: bool = False,
        replayed: bool = False,
        decoder: HistoryDecoder | None = None,
    ) -> GroupProgress:
        decoder = decoder if decoder is not None else HistoryDecoder()
        budget = group_budget(records, group_id, decoder=decoder)
        selected = admit_group_snapshots(records, group_id, decoder=decoder)
        histories = tuple(
            replace(
                history_from_records(records, member.run_id, verify_group=False, decoder=decoder),
                group=budget,
            )
            for member in budget.group.members
        )
        members = tuple(progress_view(history, active=active) for history in histories)
        latest = selected[-1] if selected else None
        return GroupProgress(
            group_id,
            budget.group.kind,
            members,
            budget.used,
            budget.group.max_attempts,
            budget.remaining,
            latest.id if latest else None,
            replayed,
            identities=tuple(
                MemberIdentity(
                    h.manifest.option_order,
                    tuple(request_identity(c.case_id, c.input_hash, c.request) for c in h.prepared),
                    h.manifest.id,
                )
                for h in histories
            ),
            initial_requests=sum(m.initial_requests for m in budget.group.members),
            independent_case_count=len(
                {(m.dataset_id, c.case_id) for m in members for c in m.cases}
            ),
            algorithm="deykit-choice-order-v1" if budget.group.kind == "choice_order" else None,
            seed=GroupExecutionService._seed(budget.group),
        )

    def preview_resume(
        self,
        group_id: str,
        *,
        retry_unknown: bool = False,
        expected_kind: GroupKind | None = None,
    ) -> GroupResumePreview:
        identifier(group_id)
        self._validate_expected_kind(expected_kind)
        if type(retry_unknown) is not bool:
            fail("invalid_unknown_retry_choice")
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
            budget = group_budget(records, group_id, decoder=self.repo.decoder)
            self._require_kind(budget.group, expected_kind)
            admit_group_snapshots(records, group_id, decoder=self.repo.decoder)
            histories = tuple(
                history_from_records(
                    records, member.run_id, verify_group=False, decoder=self.repo.decoder
                )
                for member in budget.group.members
            )
            blocked_profiles = self._failed_provider_profiles(histories)
            if blocked_profiles and budget.group.kind != "experiment":
                fail("provider_wide_failure_requires_new_run", "preflight_failed")
            for history in histories:
                if history.manifest.provider_config_hash not in blocked_profiles:
                    self._backend_captured(history, records)
            segment_ids = tuple(segment.id for segment in budget.segments)
            members = tuple(
                GroupMemberResumePreview(
                    history.manifest.id,
                    tuple(
                        item.prepared.case_id
                        for item in history.work(retry_unknown=retry_unknown)
                        if history.manifest.provider_config_hash not in blocked_profiles
                    ),
                )
                for history in histories
            )
            proposed_attempt_limit = budget.group.max_attempts

        # Do not touch the execution lock until captured admission and preflight succeed.
        active = self.runner.execution.execution_active()
        progress = self.captured_progress(records, group_id, active=active)
        return GroupResumePreview(
            group=progress,
            segment_ids=segment_ids,
            members=members,
            retry_unknown=retry_unknown,
            proposed_attempt_limit=proposed_attempt_limit,
        )

    @staticmethod
    def _failed_provider_profiles(histories: tuple[RunHistory, ...]) -> set[str]:
        return {
            history.manifest.provider_config_hash
            for history in histories
            if any(
                event.outcome and event.outcome.provider_wide for event in history.attempt_events
            )
        }

    def cancel(
        self,
        group_id: str,
        *,
        operation_id: str,
        expected_kind: GroupKind | None = None,
    ) -> GroupProgress:
        identifier(group_id)
        identifier(operation_id)
        self._validate_expected_kind(expected_kind)
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
            budget = group_budget(records, group_id, decoder=self.repo.decoder)
            self._require_kind(budget.group, expected_kind)
            admit_group_snapshots(records, group_id, decoder=self.repo.decoder)
            group = budget.group

        for member in group.members:
            child_operation_id = "group-cancel-" + safe_hash(
                {
                    "command": "execution_group.cancel.child-v1",
                    "operation_id": operation_id,
                    "group_id": group.id,
                    "run_id": member.run_id,
                }
            )
            try:
                self.runner.cancel(member.run_id, operation_id=child_operation_id)
            except ServiceFailure as failure:
                raise ServiceFailure(
                    failure.error.model_copy(update={"resource_id": group.id})
                ) from None

        active = self.runner.execution.execution_active()
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
        return self.captured_progress(records, group.id, active=active, decoder=self.repo.decoder)

    async def start(
        self,
        *,
        selection_source: JsonSource,
        prepare: Callable[[], GroupPlan],
        operation_id: str,
        expected_review_context_hash: str | None = None,
        on_created: GroupAcknowledgementCallback | None = None,
    ) -> GroupProgress:
        identifier(operation_id)
        if type(selection_source) is not str:
            fail("invalid_group_selection")
        selection = encode_group_start_selection(
            selection_source,
            expected_review_context_hash=expected_review_context_hash,
        )
        digest = group_start_intent(selection)
        if on_created is not None:
            acknowledged = self._capture_acknowledgement(
                operation_id, digest, command="start", replayed=True
            )
            if acknowledged is not None:
                await self._notify_acknowledged(
                    on_created, acknowledged, reason="group_created_callback_failed"
                )
                return acknowledged.progress
        else:
            receipt = self._receipt(operation_id, digest)
            if receipt is not None:
                return self._replay(receipt)
        try:
            with self.runner.execution.execution_owner():
                if on_created is not None:
                    acknowledged = self._capture_acknowledgement(
                        operation_id, digest, command="start", replayed=True
                    )
                    if acknowledged is not None:
                        await self._notify_acknowledged(
                            on_created, acknowledged, reason="group_created_callback_failed"
                        )
                        return acknowledged.progress
                else:
                    receipt = self._receipt(operation_id, digest)
                    if receipt is not None:
                        return self._replay(receipt)
                plan = prepare()
                with self.source.consistent_read():
                    receipt = self.source.operation_receipt(operation_id, intent_hash=digest)
                    if receipt is not None:
                        pass
                    else:
                        self._check_selection(plan)
                        self.runner.planner.check_contexts(plan.plans)
                        require_review_hash(
                            expected_review_context_hash,
                            group_review_hash(plan, selection_source),
                        )
                        group, changes = self.store.stage_freeze(
                            plan, operation_id, digest, selection.stored_source
                        )
                        staged_records = tuple(
                            StoredRecord(item.key, item.body, bytes_hash(item.body))
                            for item in changes
                            if item.body is not None
                        )
                        segment, segment_changes = self.store.stage_segment(
                            group, operation_id, 1, False, staged_records, initial=True
                        )
                        all_changes = (*changes, *segment_changes)
                        ready_changes = self.store.stage_ready(segment, self._staged(all_changes))
                        self._check_size((*all_changes, *ready_changes), kind=plan.kind)
                        deadline = self.repo.clock.monotonic() + group.deadline_seconds
                        self.source.commit(operation_id, all_changes, intent_hash=digest)
                        self.store.ready(segment, acknowledge=False)
                if receipt is not None:
                    if on_created is not None:
                        acknowledged = self._capture_acknowledgement(
                            operation_id, digest, command="start", replayed=True
                        )
                        if acknowledged is None:
                            self._acknowledgement_incomplete(self._receipt_group_id(receipt))
                        await self._notify_acknowledged(
                            on_created, acknowledged, reason="group_created_callback_failed"
                        )
                        return acknowledged.progress
                    return self._replay(receipt)
                if on_created is not None:
                    acknowledged = await self.runner.scheduler._source_call(
                        group.id,
                        "history",
                        lambda: self._capture_acknowledgement(
                            operation_id, digest, command="start", replayed=False, active=True
                        ),
                        offload=True,
                    )
                    if acknowledged is None:
                        self._acknowledgement_incomplete(group.id)
                    acknowledged = self._observe_owned_acknowledgement(acknowledged)
                    await self._notify_acknowledged(
                        on_created, acknowledged, reason="group_created_callback_failed"
                    )
                return await self._execute(group, segment, deadline=deadline)
        except ServiceFailure as failure:
            if failure.error.code == "execution_locked":
                receipt = self._receipt(operation_id, digest)
                if receipt is not None:
                    if on_created is not None:
                        acknowledged = self._capture_acknowledgement(
                            operation_id, digest, command="start", replayed=True
                        )
                        if acknowledged is None:
                            self._acknowledgement_incomplete(self._receipt_group_id(receipt))
                        await self._notify_acknowledged(
                            on_created, acknowledged, reason="group_created_callback_failed"
                        )
                        return acknowledged.progress
                    return self._replay(receipt)
            raise

    async def resume(
        self,
        group_id: str,
        *,
        operation_id: str,
        retry_unknown: bool = False,
        expected_kind: GroupKind | None = None,
        on_resumed: GroupAcknowledgementCallback | None = None,
    ) -> GroupProgress:
        identifier(group_id)
        identifier(operation_id)
        if expected_kind is not None and expected_kind not in (
            "choice_order",
            "regression_check",
            "experiment",
        ):
            fail("invalid_execution_group_kind")
        if type(retry_unknown) is not bool:
            fail("invalid_unknown_retry_choice")
        digest = safe_hash(
            {
                "command": "execution_group.resume",
                "group_id": group_id,
                "retry_unknown": retry_unknown,
            }
        )
        if on_resumed is not None:
            acknowledged = self._capture_acknowledgement(
                operation_id,
                digest,
                command="resume",
                requested_group_id=group_id,
                expected_kind=expected_kind,
                retry_unknown=retry_unknown,
                replayed=True,
            )
            if acknowledged is not None:
                await self._notify_acknowledged(
                    on_resumed, acknowledged, reason="group_resumed_callback_failed"
                )
                return acknowledged.progress
        else:
            receipt = self._receipt(operation_id, digest)
            if receipt is not None:
                self._admit_resume_receipt_kind(
                    receipt,
                    operation_id=operation_id,
                    group_id=group_id,
                    retry_unknown=retry_unknown,
                    expected_kind=expected_kind,
                )
                return self._replay(receipt)
        try:
            with self.runner.execution.execution_owner():
                if on_resumed is not None:
                    acknowledged = self._capture_acknowledgement(
                        operation_id,
                        digest,
                        command="resume",
                        requested_group_id=group_id,
                        expected_kind=expected_kind,
                        retry_unknown=retry_unknown,
                        replayed=True,
                    )
                    if acknowledged is not None:
                        await self._notify_acknowledged(
                            on_resumed, acknowledged, reason="group_resumed_callback_failed"
                        )
                        return acknowledged.progress
                else:
                    receipt = self._receipt(operation_id, digest)
                    if receipt is not None:
                        self._admit_resume_receipt_kind(
                            receipt,
                            operation_id=operation_id,
                            group_id=group_id,
                            retry_unknown=retry_unknown,
                            expected_kind=expected_kind,
                        )
                        return self._replay(receipt)
                with self.source.consistent_read():
                    receipt = self.source.operation_receipt(operation_id, intent_hash=digest)
                    if receipt is None:
                        records = self.source.capture_snapshot()
                        budget = group_budget(records, group_id, decoder=self.repo.decoder)
                        self._require_kind(budget.group, expected_kind)
                        admit_group_snapshots(records, group_id, decoder=self.repo.decoder)
                        histories = tuple(
                            history_from_records(
                                records,
                                member.run_id,
                                verify_group=False,
                                decoder=self.repo.decoder,
                            )
                            for member in budget.group.members
                        )
                        blocked_profiles = self._failed_provider_profiles(histories)
                        if blocked_profiles and budget.group.kind != "experiment":
                            fail("provider_wide_failure_requires_new_run", "preflight_failed")
                        segments = sorted(
                            (
                                decoded(ExecutionGroupSegment, r)
                                for r in records
                                if r.key.collection == "group_segments"
                                and r.key.scope == (group_id,)
                            ),
                            key=lambda s: s.sequence,
                        )
                        if tuple(s.sequence for s in segments) != tuple(
                            range(1, len(segments) + 1)
                        ):
                            fail("invalid_group_segment_sequence", "incompatible_data")
                        # Credential/config failure remains zero-write for this new segment.
                        for history in histories:
                            needs_backend = budget.group.kind != "experiment" or (
                                bool(history.work(retry_unknown=retry_unknown))
                                and budget.remaining_for(history.manifest.id) > 0
                            )
                            if (
                                needs_backend
                                and history.manifest.provider_config_hash not in blocked_profiles
                            ):
                                self._backend_captured(history, records)
                        # Recover unknowns while holding actual execution ownership; no sends.
                        for member in budget.group.members:
                            self.repo.recover(member.run_id)
                        records = self.source.capture_snapshot()
                        if budget.segments:
                            self.store.snapshot(budget.group, budget.segments[-1])
                            records = self.source.capture_snapshot()
                        segment, changes = self.store.stage_segment(
                            budget.group,
                            operation_id,
                            len(segments) + 1,
                            retry_unknown,
                            records,
                            initial=False,
                        )
                        deadline = self.repo.clock.monotonic() + budget.group.deadline_seconds
                        self.source.commit(operation_id, changes, intent_hash=digest)
                        self.store.ready(segment, acknowledge=True)
                if receipt is not None:
                    if on_resumed is not None:
                        acknowledged = self._capture_acknowledgement(
                            operation_id,
                            digest,
                            command="resume",
                            requested_group_id=group_id,
                            expected_kind=expected_kind,
                            retry_unknown=retry_unknown,
                            replayed=True,
                        )
                        if acknowledged is None:
                            self._acknowledgement_incomplete(group_id)
                        await self._notify_acknowledged(
                            on_resumed, acknowledged, reason="group_resumed_callback_failed"
                        )
                        return acknowledged.progress
                    self._admit_resume_receipt_kind(
                        receipt,
                        operation_id=operation_id,
                        group_id=group_id,
                        retry_unknown=retry_unknown,
                        expected_kind=expected_kind,
                    )
                    return self._replay(receipt)
                if on_resumed is not None:
                    acknowledged = await self.runner.scheduler._source_call(
                        group_id,
                        "history",
                        lambda: self._capture_acknowledgement(
                            operation_id,
                            digest,
                            command="resume",
                            requested_group_id=group_id,
                            expected_kind=expected_kind,
                            retry_unknown=retry_unknown,
                            replayed=False,
                            active=True,
                        ),
                        offload=True,
                    )
                    if acknowledged is None:
                        self._acknowledgement_incomplete(group_id)
                    acknowledged = self._observe_owned_acknowledgement(acknowledged)
                    await self._notify_acknowledged(
                        on_resumed, acknowledged, reason="group_resumed_callback_failed"
                    )
                return await self._execute(
                    budget.group, segment, deadline=deadline, blocked_profiles=blocked_profiles
                )
        except ServiceFailure as failure:
            if failure.error.code == "execution_locked":
                receipt = self._receipt(operation_id, digest)
                if receipt is not None:
                    if on_resumed is not None:
                        acknowledged = self._capture_acknowledgement(
                            operation_id,
                            digest,
                            command="resume",
                            requested_group_id=group_id,
                            expected_kind=expected_kind,
                            retry_unknown=retry_unknown,
                            replayed=True,
                        )
                        if acknowledged is None:
                            self._acknowledgement_incomplete(group_id)
                        await self._notify_acknowledged(
                            on_resumed, acknowledged, reason="group_resumed_callback_failed"
                        )
                        return acknowledged.progress
                    self._admit_resume_receipt_kind(
                        receipt,
                        operation_id=operation_id,
                        group_id=group_id,
                        retry_unknown=retry_unknown,
                        expected_kind=expected_kind,
                    )
                    return self._replay(receipt)
            raise

    async def _execute(
        self,
        group: ExecutionGroup,
        segment: ExecutionGroupSegment,
        *,
        deadline: float,
        blocked_profiles: set[str] | None = None,
    ) -> GroupProgress:
        stop_reason: ServiceError | None = None
        stop_state: Literal["cancelled", "interrupted", "budget_exhausted"] = "interrupted"
        try:
            if group.kind == "experiment":
                stop_state, stop_reason = await self._execute_experiment(
                    group, segment, deadline=deadline, blocked_profiles=blocked_profiles
                )
            else:
                stop_state, stop_reason = await self._execute_sequential(segment, deadline=deadline)
        finally:
            # Unsettled children stay explicit; these are references, not synthetic answers.
            for child in segment.member_segments:

                def finalize_child(member: GroupMemberSegment = child) -> None:
                    history = self.repo.history(member.run_id)
                    if history.state in {"running", "preparing", "cancelling"}:
                        results = history.results()
                        state: Literal[
                            "completed",
                            "completed_with_errors",
                            "cancelled",
                            "interrupted",
                            "budget_exhausted",
                        ]
                        state = (
                            "completed"
                            if all(r.status == "valid" for r in results)
                            else "completed_with_errors"
                            if not any(r.status == "pending" for r in results)
                            else stop_state
                        )
                        self.repo.finish(member.run_id, state, member.segment_id, stop_reason)

                await self.runner.scheduler._source_call(
                    child.run_id, "finalization", finalize_child, offload=True
                )
            await self.runner.scheduler._source_call(
                group.id, "finalization", lambda: self.store.snapshot(group, segment), offload=True
            )
        records = await self.runner.scheduler._source_call(
            group.id, "history", self.source.capture_snapshot, offload=True
        )
        return self.captured_progress(records, group.id, active=True, decoder=self.repo.decoder)

    async def _execute_sequential(
        self, segment: ExecutionGroupSegment, *, deadline: float
    ) -> tuple[Literal["cancelled", "interrupted", "budget_exhausted"], ServiceError | None]:
        stop_state: Literal["cancelled", "interrupted", "budget_exhausted"] = "interrupted"
        stop_reason: ServiceError | None = None
        for member in segment.member_segments:

            def capture(member: GroupMemberSegment = member) -> tuple[RunHistory, RunSegment, bool]:
                history = self.repo.history(member.run_id)
                child = next((s for s in history.segments if s.id == member.segment_id), None)
                if child is None or not any(
                    e.state == "segment_ready" and e.segment_id == member.segment_id
                    for e in history.events
                ):
                    fail("execution_group_not_ready", "run_incomplete")
                return history, child, self.repo.cancelled(history, child)

            history, child_segment, cancelled = await self.runner.scheduler._source_call(
                member.run_id, "history", capture, offload=True
            )
            if cancelled:
                stop_state = "cancelled"
                stop_reason = ServiceError(code="run_incomplete", reason="cancel_requested")
                break
            if history.work(retry_unknown=segment.retry_unknown) and (
                self.repo.clock.monotonic() >= deadline or history.remaining <= 0
            ):
                stop_state = "budget_exhausted"
                stop_reason = ServiceError(
                    code="run_incomplete",
                    reason="segment_deadline"
                    if self.repo.clock.monotonic() >= deadline
                    else "execution_group_cap",
                )
                break

            def resolve_backend(history: RunHistory = history) -> Backend:
                return self.runner._backend(history)

            backend = await self.runner.scheduler._source_call(
                member.run_id, "history", resolve_backend, offload=True
            )
            result = await self.runner.scheduler.run(
                history, child_segment, backend, deadline=deadline
            )
            if result.state in {"cancelled", "interrupted", "budget_exhausted"} or any(
                event.outcome and event.outcome.provider_wide for event in result.attempt_events
            ):
                stop_state = cast(
                    Literal["cancelled", "interrupted", "budget_exhausted"],
                    (
                        result.state
                        if result.state in {"cancelled", "interrupted", "budget_exhausted"}
                        else "interrupted"
                    ),
                )
                stop_reason = result.events[-1].reason or ServiceError(
                    code="run_incomplete", reason="provider_wide_failure"
                )
                break
        return stop_state, stop_reason

    async def _execute_experiment(
        self,
        group: ExecutionGroup,
        segment: ExecutionGroupSegment,
        *,
        deadline: float,
        blocked_profiles: set[str] | None = None,
    ) -> tuple[Literal["cancelled", "interrupted", "budget_exhausted"], ServiceError | None]:
        from deykit.runner.group_evidence import experiment_request
        from deykit.runner.scheduler import ConcurrencyShare, ProviderStop, _SegmentDeadlineElapsed

        concurrency = experiment_request(group).settings.concurrency
        source_gate = asyncio.Lock()
        provider_stops = {
            profile: ProviderStop(failed=True) for profile in (blocked_profiles or set())
        }
        stop_state: Literal["cancelled", "interrupted", "budget_exhausted"] = "interrupted"
        stop_reason: ServiceError | None = None
        tasks: dict[asyncio.Task[RunHistory], tuple[ConcurrencyShare, str]] = {}
        remaining = iter(segment.member_segments)

        async def launch(member: GroupMemberSegment, slots: int) -> str | None:
            def capture() -> tuple[RunHistory, RunSegment, Backend | None, bool, str | None]:
                history = self.repo.history(member.run_id)
                child = next((s for s in history.segments if s.id == member.segment_id), None)
                if child is None or not any(
                    e.state == "segment_ready" and e.segment_id == child.id for e in history.events
                ):
                    fail("execution_group_not_ready", "run_incomplete")
                stop = provider_stops.get(history.manifest.provider_config_hash)
                work = history.work(retry_unknown=segment.retry_unknown)
                skip = (
                    "provider_skipped"
                    if stop is not None and stop.failed
                    else "no_work"
                    if not work
                    else self.runner.scheduler._cap_reason(history)
                    if history.remaining <= 0
                    else None
                )
                backend = None if skip else self.runner._backend(history)
                return history, child, backend, self.repo.cancelled(history, child), skip

            try:
                history, child, backend, cancelled, skip = await self.runner.scheduler._source_call(
                    member.run_id,
                    "history",
                    capture,
                    deadline=deadline,
                    offload=True,
                    source_gate=source_gate,
                )
            except _SegmentDeadlineElapsed:
                return "segment_deadline"
            if cancelled:
                return "cancel_requested"
            if skip is not None:
                return skip
            provider_stop = provider_stops.setdefault(
                history.manifest.provider_config_hash, ProviderStop()
            )
            if provider_stop.failed:
                return "provider_skipped"
            assert backend is not None
            share = ConcurrencyShare(slots)
            task = asyncio.create_task(
                self.runner.scheduler.run(
                    history,
                    child,
                    backend,
                    deadline=deadline,
                    concurrency_override=slots,
                    source_gate=source_gate,
                    provider_stop=provider_stop,
                    concurrency_share=share,
                )
            )
            tasks[task] = (share, history.manifest.provider_config_hash)
            return None

        async def launch_next(slots: int) -> str | None:
            nonlocal stop_state, stop_reason
            while (member := next(remaining, None)) is not None:
                problem = await launch(member, slots)
                if problem in {"provider_skipped", "no_work"}:
                    continue
                if problem in {
                    "execution_group_cap",
                    "experiment_reservation_budget",
                    "attempt_cap",
                }:
                    stop_state = "budget_exhausted"
                    stop_reason = ServiceError(code="run_incomplete", reason=problem)
                    continue
                return problem
            return None

        def distribute(slots: int) -> None:
            if slots and tasks:
                shares = [share for share, _ in tasks.values()]
                per_member, extra = divmod(slots, len(shares))
                for index, share in enumerate(shares):
                    added = per_member + (1 if index < extra else 0)
                    if added:
                        share.add(added)

        try:
            initial_count = min(concurrency, len(segment.member_segments))
            slots, extra = divmod(concurrency, initial_count)
            unallocated = 0
            for index in range(initial_count):
                available = slots + (1 if index < extra else 0)
                before = len(tasks)
                problem = await launch_next(available)
                if problem is not None:
                    return (
                        "cancelled"
                        if problem == "cancel_requested"
                        else "budget_exhausted"
                        if problem == "segment_deadline"
                        else "interrupted",
                        ServiceError(code="run_incomplete", reason=problem),
                    )
                if len(tasks) == before:
                    unallocated += available
            distribute(unallocated)
            while tasks:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                released = [tasks.pop(task) for task in done]
                completed = await asyncio.gather(*done, return_exceptions=True)
                for result, (_, profile) in zip(completed, released, strict=True):
                    if isinstance(result, BaseException):
                        raise result
                    provider_wide = any(
                        event.outcome and event.outcome.provider_wide
                        for event in result.attempt_events
                    )
                    if result.state == "cancelled" or (
                        result.state == "interrupted" and not provider_stops[profile].failed
                    ):
                        stop_state = "cancelled" if result.state == "cancelled" else "interrupted"
                        stop_reason = result.events[-1].reason or ServiceError(
                            code="run_incomplete", reason="provider_wide_failure"
                        )
                        return stop_state, stop_reason
                    if provider_wide or provider_stops[profile].failed:
                        stop_reason = provider_stops[profile].reason or ServiceError(
                            code="run_incomplete", reason="provider_wide_failure"
                        )
                    if result.state == "budget_exhausted":
                        stop_state = "budget_exhausted"
                        stop_reason = result.events[-1].reason
                unallocated = 0
                for share, _ in released:
                    before = len(tasks)
                    problem = await launch_next(share.limit)
                    if problem is not None:
                        return (
                            "cancelled"
                            if problem == "cancel_requested"
                            else "budget_exhausted"
                            if problem == "segment_deadline"
                            else "interrupted",
                            ServiceError(code="run_incomplete", reason=problem),
                        )
                    if len(tasks) == before:
                        unallocated += share.limit
                distribute(unallocated)
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                drained = asyncio.gather(*tasks, return_exceptions=True)
                cancelled = False
                while not drained.done():
                    try:
                        await asyncio.shield(drained)
                    except asyncio.CancelledError:
                        cancelled = True
                if cancelled:
                    raise asyncio.CancelledError
        return stop_state, stop_reason
