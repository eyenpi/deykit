"""Stage atomic group/member evidence and append immutable group result boundaries."""

from deykit.application.dataset_support import fail
from deykit.contracts.codec import load_record
from deykit.contracts.execution_groups import (
    CheckSnapshot,
    DiagnosticSnapshot,
    ExecutionGroup,
    ExecutionGroupSegment,
    ExecutionMember,
    GroupMemberSegment,
    MemberResult,
)
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import SourceChange, StoredRecord
from deykit.contracts.records import RunSegment
from deykit.runner.group_evidence import (
    admit_group_snapshots,
    content_hash,
    member_prepared_hash,
)
from deykit.runner.group_models import GroupPlan
from deykit.runner.history import history_from_records
from deykit.runner.planner import MAX_PLAN_BYTES
from deykit.runner.repository import RunRepository, change, deadline_at


class GroupRepository:
    def __init__(self, repo: RunRepository) -> None:
        self.repo, self.source = repo, repo.source

    def stage_freeze(
        self, plan: GroupPlan, operation_id: str, digest: str, selection_source: str
    ) -> tuple[ExecutionGroup, tuple[SourceChange, ...]]:
        plan.validate()
        group_id = self.repo.identity()
        changes: list[SourceChange] = []
        members: list[ExecutionMember] = []
        for child in plan.plans:
            run_id = self.repo.identity()
            staged = self.repo.stage_freeze(child, operation_id, run_id=run_id, group_id=group_id)
            body = next(item.body for item in staged if item.key.collection == "runs")
            if body is None:
                fail("invalid_staged_group", "internal_error")
            staged_records = tuple(
                StoredRecord(item.key, item.body, bytes_hash(item.body))
                for item in staged
                if item.body is not None
            )
            try:
                prepared_hash = member_prepared_hash(
                    run_id, tuple(case.id for case in child.cases), staged_records
                )
            except ValueError:
                fail("invalid_staged_group_prepared_evidence", "internal_error")
            members.append(
                ExecutionMember(
                    run_id=run_id,
                    manifest_hash=bytes_hash(body),
                    prepared_hash=prepared_hash,
                    initial_requests=child.initial_requests,
                )
            )
            changes.extend(staged)
        group = ExecutionGroup(
            id=group_id,
            kind=plan.kind,
            members=tuple(members),
            max_attempts=plan.max_attempts,
            deadline_seconds=plan.deadline_seconds,
            operation_id=operation_id,
            intent_hash=digest,
            selection_source=selection_source,
            content_hash="0" * 64,
            created_at=self.repo.clock.utc_now(),
        )
        group = group.model_copy(update={"content_hash": content_hash(group)})
        changes.append(change("execution_groups", group))
        if sum(len(item.body or b"") for item in changes) > MAX_PLAN_BYTES:
            fail("execution_group_resource_limit", "preflight_failed")
        return group, tuple(changes)

    def stage_segment(
        self,
        group: ExecutionGroup,
        operation_id: str,
        sequence: int,
        retry_unknown: bool,
        records: tuple[StoredRecord, ...],
        *,
        initial: bool,
    ) -> tuple[ExecutionGroupSegment, tuple[SourceChange, ...]]:
        stamp = self.repo.clock.utc_now()
        deadline = deadline_at(stamp, group.deadline_seconds)
        changes: list[SourceChange] = []
        members: list[GroupMemberSegment] = []
        for member in group.members:
            history = history_from_records(records, member.run_id)
            child = RunSegment(
                id=self.repo.identity(),
                run_id=member.run_id,
                sequence=len(history.segments) + 1,
                retry_unknown=retry_unknown,
                started_at=stamp,
                deadline_at=deadline,
                cancel_through_sequence=0 if initial else len(history.controls),
            )
            members.append(GroupMemberSegment(run_id=member.run_id, segment_id=child.id))
            changes.extend(
                (
                    change("segments", child, (member.run_id,)),
                    change(
                        "run_events",
                        self.repo.event(history, "running", segment_id=child.id),
                        (member.run_id,),
                    ),
                )
            )
        segment = ExecutionGroupSegment(
            id=self.repo.identity(),
            group_id=group.id,
            sequence=sequence,
            operation_id=operation_id,
            retry_unknown=retry_unknown,
            member_segments=tuple(members),
            started_at=stamp,
            deadline_at=deadline,
        )
        changes.append(change("group_segments", segment, (group.id,)))
        return segment, tuple(changes)

    def stage_ready(
        self, segment: ExecutionGroupSegment, records: tuple[StoredRecord, ...]
    ) -> tuple[SourceChange, ...]:
        return tuple(
            change(
                "run_events",
                self.repo.event(
                    history_from_records(records, child.run_id),
                    "segment_ready",
                    segment_id=child.segment_id,
                ),
                (child.run_id,),
            )
            for child in segment.member_segments
        )

    def ready(self, segment: ExecutionGroupSegment, *, acknowledge: bool) -> None:
        # The caller retains source ownership from segment freeze through acknowledgements.
        with self.source.consistent_read():
            if acknowledge:
                for child in segment.member_segments:
                    self.repo.execution.acknowledge_cancel(child.run_id, child.segment_id)
            records = self.source.capture_snapshot()
            changes = self.stage_ready(segment, records)
            self.source.commit(self.repo.identity(), changes)

    def snapshot(self, group: ExecutionGroup, segment: ExecutionGroupSegment) -> None:
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
            previous_admitted = admit_group_snapshots(records, group.id)
            results = tuple(
                MemberResult(
                    run_id=member.run_id,
                    result_snapshot_id=history_from_records(records, member.run_id)
                    .snapshots[-1]
                    .id,
                )
                for member in group.members
            )
            if any(s.segment_id == segment.id and s.results == results for s in previous_admitted):
                return
            kind: type[DiagnosticSnapshot] | type[CheckSnapshot] = (
                DiagnosticSnapshot if group.kind == "choice_order" else CheckSnapshot
            )
            collection = "diagnostic_snapshots" if kind is DiagnosticSnapshot else "check_snapshots"
            previous = tuple(
                load_record(kind, r.body) for r in records if r.key.collection == collection
            )
            sequence = 1 + sum(r.group_id == group.id for r in previous)
            record = kind(
                id=self.repo.identity(),
                sequence=sequence,
                group_id=group.id,
                segment_id=segment.id,
                results=results,
                content_hash="0" * 64,
                created_at=self.repo.clock.utc_now(),
            )
            record = record.model_copy(update={"content_hash": content_hash(record)})
            self.source.commit(
                self.repo.identity(),
                (
                    change(
                        "diagnostic_snapshots" if kind is DiagnosticSnapshot else "check_snapshots",
                        record,
                    ),
                ),
            )
