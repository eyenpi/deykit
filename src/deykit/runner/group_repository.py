"""Stage atomic group/member evidence and append immutable group result boundaries."""

from deykit.application.dataset_support import fail
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import load_record
from deykit.contracts.execution_groups import (
    CheckSnapshot,
    DiagnosticSnapshot,
    ExecutionGroup,
    ExecutionGroupSegment,
    ExecutionMember,
    ExperimentSnapshot,
    GroupMemberSegment,
    MemberResult,
)
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import Collection, SourceChange, StoredRecord
from deykit.contracts.records import RunSegment
from deykit.runner.group_evidence import (
    admit_group_snapshots,
    content_hash,
    group_budget,
    member_prepared_hash,
)
from deykit.runner.group_models import GroupPlan
from deykit.runner.group_selection import decode_group_start_selection, group_start_intent
from deykit.runner.history import history_from_records
from deykit.runner.planner import MAX_EXPERIMENT_PLAN_BYTES, MAX_PLAN_BYTES
from deykit.runner.repository import RunRepository, change, deadline_at


class GroupRepository:
    def __init__(self, repo: RunRepository) -> None:
        self.repo, self.source = repo, repo.source

    def stage_freeze(
        self, plan: GroupPlan, operation_id: str, digest: str, selection_source: str
    ) -> tuple[ExecutionGroup, tuple[SourceChange, ...]]:
        plan.validate()
        selection = decode_group_start_selection(selection_source, expected_kind=plan.kind)
        if group_start_intent(selection) != digest:
            fail("group_selection_intent_mismatch", "conflict")
        group_id = self.repo.identity()
        changes: list[SourceChange] = []
        members: list[ExecutionMember] = []
        limit = MAX_EXPERIMENT_PLAN_BYTES if plan.kind == "experiment" else MAX_PLAN_BYTES
        size = 0
        for child in plan.plans:
            run_id = self.repo.identity()
            try:
                staged = self.repo.stage_freeze(
                    child,
                    operation_id,
                    run_id=run_id,
                    group_id=group_id,
                    max_plan_bytes=limit - size if plan.kind == "experiment" else None,
                )
            except ServiceFailure as error:
                if plan.kind == "experiment" and error.error.reason == "run_resource_limit":
                    fail("execution_group_resource_limit", "preflight_failed")
                raise
            size += sum(len(item.body or b"") for item in staged)
            if size > limit:
                fail("execution_group_resource_limit", "preflight_failed")
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
        if size + len(changes[-1].body or b"") > limit:
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
        if group_budget(records, group.id, decoder=self.repo.decoder).group != group:
            fail("execution_group_context_mismatch", "incompatible_data")
        for member in group.members:
            history = history_from_records(
                records, member.run_id, verify_group=False, decoder=self.repo.decoder
            )
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
        budget = group_budget(records, segment.group_id, decoder=self.repo.decoder)
        if segment not in budget.segments:
            fail("group_segment_identity_mismatch", "incompatible_data")
        return tuple(
            change(
                "run_events",
                self.repo.event(
                    history_from_records(
                        records, child.run_id, verify_group=False, decoder=self.repo.decoder
                    ),
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
            previous_admitted = admit_group_snapshots(records, group.id, decoder=self.repo.decoder)
            if group_budget(records, group.id, decoder=self.repo.decoder).group != group:
                fail("execution_group_context_mismatch", "incompatible_data")
            results = tuple(
                MemberResult(
                    run_id=member.run_id,
                    result_snapshot_id=history_from_records(
                        records, member.run_id, verify_group=False, decoder=self.repo.decoder
                    )
                    .snapshots[-1]
                    .id,
                )
                for member in group.members
            )
            if any(s.segment_id == segment.id and s.results == results for s in previous_admitted):
                return
            kind: type[DiagnosticSnapshot] | type[CheckSnapshot] | type[ExperimentSnapshot]
            collection: Collection
            if group.kind == "choice_order":
                kind, collection = DiagnosticSnapshot, "diagnostic_snapshots"
                previous_count = sum(
                    load_record(DiagnosticSnapshot, r.body).group_id == group.id
                    for r in records
                    if r.key.collection == collection
                )
            elif group.kind == "regression_check":
                kind, collection = CheckSnapshot, "check_snapshots"
                previous_count = sum(
                    load_record(CheckSnapshot, r.body).group_id == group.id
                    for r in records
                    if r.key.collection == collection
                )
            else:
                kind, collection = ExperimentSnapshot, "experiment_snapshots"
                previous_count = sum(
                    load_record(ExperimentSnapshot, r.body).group_id == group.id
                    for r in records
                    if r.key.collection == collection
                )
            sequence = 1 + previous_count
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
                        collection,
                        record,
                    ),
                ),
            )
