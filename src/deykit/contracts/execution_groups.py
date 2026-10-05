"""Immutable bounded execution groups and their frozen result references."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.json_value import JsonSource
from deykit.contracts.records import HashedRecord, NonnegativeInt, PositiveInt, UtcTimestamp


class ExecutionMember(FrozenModel):
    run_id: ResourceId
    manifest_hash: ContentHash
    prepared_hash: ContentHash
    initial_requests: NonnegativeInt


class ExecutionGroup(HashedRecord):
    id: ResourceId
    kind: Literal["choice_order", "regression_check"]
    members: Annotated[tuple[ExecutionMember, ...], Field(min_length=1, max_length=10_000)]
    max_attempts: PositiveInt
    deadline_seconds: Annotated[int, Field(ge=1, le=86_400)]
    operation_id: ResourceId
    intent_hash: ContentHash
    selection_source: JsonSource
    content_hash: ContentHash
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def bounded_members(self) -> Self:
        if len({member.run_id for member in self.members}) != len(self.members):
            raise ValueError("duplicate_execution_member")
        if self.kind == "choice_order" and len(self.members) > 4:
            raise ValueError("too_many_diagnostic_orders")
        if sum(member.initial_requests for member in self.members) > self.max_attempts:
            raise ValueError("group_initial_requests_exceed_cap")
        return self


class GroupMemberSegment(FrozenModel):
    run_id: ResourceId
    segment_id: ResourceId


class ExecutionGroupSegment(Record):
    id: ResourceId
    group_id: ResourceId
    sequence: PositiveInt
    operation_id: ResourceId
    retry_unknown: bool = False
    member_segments: tuple[GroupMemberSegment, ...]
    started_at: UtcTimestamp
    deadline_at: UtcTimestamp


class MemberResult(FrozenModel):
    run_id: ResourceId
    result_snapshot_id: ResourceId


class DiagnosticSnapshot(HashedRecord):
    id: ResourceId
    sequence: PositiveInt
    group_id: ResourceId
    segment_id: ResourceId | None = None
    results: tuple[MemberResult, ...]
    content_hash: ContentHash
    created_at: UtcTimestamp


class CheckSnapshot(HashedRecord):
    id: ResourceId
    sequence: PositiveInt
    group_id: ResourceId
    segment_id: ResourceId | None = None
    results: tuple[MemberResult, ...]
    baseline_unavailable: Literal["frozen_regression_selection"] = "frozen_regression_selection"
    content_hash: ContentHash
    created_at: UtcTimestamp


class RegressionRemoval(Record):
    id: ResourceId
    regression_id: ResourceId
    decision_id: ResourceId
    operation_id: ResourceId
    created_at: UtcTimestamp
