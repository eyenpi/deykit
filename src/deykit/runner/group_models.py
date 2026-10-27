"""Typed execution-group preparation and safe progress views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from deykit.application.dataset_support import fail
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import CompiledRequest
from deykit.runner.planner import RunPlan
from deykit.runner.views import RunPreview, RunProgress

GroupKind = Literal["choice_order", "regression_check", "experiment"]


@dataclass(frozen=True)
class GroupPlan:
    kind: GroupKind
    plans: tuple[RunPlan, ...]
    max_attempts: int
    deadline_seconds: int
    default_regression_ids: tuple[str, ...] | None = None
    review_membership_records: tuple[StoredRecord, ...] = field(kw_only=True)

    def validate(self) -> None:
        if self.kind not in ("choice_order", "regression_check", "experiment") or not self.plans:
            fail("invalid_execution_group", "preflight_failed")
        if self.kind == "choice_order":
            if len(self.plans) > 4:
                fail("too_many_diagnostic_orders", "preflight_failed")
            first = self.plans[0]
            if len({p.selection.option_order for p in self.plans}) != len(self.plans) or any(
                p.definition != first.definition
                or p.cases != first.cases
                or p.labels != first.labels
                or p.development_cases != first.development_cases
                or p.development_labels != first.development_labels
                or p.provider != first.provider
                or p.selection.settings != first.selection.settings
                for p in self.plans
            ):
                fail("diagnostic_source_mismatch", "preflight_failed")
        if len(self.plans) > 10_000 or (
            self.kind != "experiment"
            and sum(p.initial_requests for p in self.plans) > self.max_attempts
        ):
            fail("group_initial_requests_exceed_cap", "preflight_failed")
        if not 1 <= self.deadline_seconds <= 86_400:
            fail("invalid_segment_deadline", "preflight_failed")
        if any(p.selection.settings.deadline_seconds != self.deadline_seconds for p in self.plans):
            fail("group_deadline_mismatch", "preflight_failed")
        if any(p.selection.settings.max_attempts != self.max_attempts for p in self.plans):
            fail("group_attempt_allocation_mismatch", "preflight_failed")
        if any(
            bool(p.selection.regression_ids) != (self.kind == "regression_check")
            for p in self.plans
        ):
            fail("group_selection_mismatch", "preflight_failed")


@dataclass(frozen=True)
class RequestIdentity:
    case_id: str
    input_hash: str
    request_hash: str | None
    compiler: str | None
    compiler_version: str | None
    requested_model: str | None
    semantic_headers_source: str | None = None


@dataclass(frozen=True)
class MemberIdentity:
    option_order: tuple[str, ...] | None
    requests: tuple[RequestIdentity, ...]
    run_id: str | None = None


@dataclass(frozen=True)
class GroupAcknowledged:
    group_id: str
    kind: GroupKind
    mode: Literal["fixture", "live"]
    segment_id: str
    replayed: bool
    member_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class GroupMemberResumePreview:
    run_id: str
    planned_case_ids: tuple[str, ...]


@dataclass(frozen=True)
class GroupResumePreview:
    group: GroupProgress
    segment_ids: tuple[str, ...]
    members: tuple[GroupMemberResumePreview, ...]
    retry_unknown: bool
    proposed_attempt_limit: int
    dry_run: bool = True


@dataclass(frozen=True)
class GroupPreview:
    kind: GroupKind
    members: tuple[RunPreview, ...]
    initial_requests: int
    attempt_limit: int
    deadline_seconds: int
    review_context_hash: str
    dry_run: bool = True
    identities: tuple[MemberIdentity, ...] = ()
    independent_case_count: int = 0
    algorithm: str | None = None
    seed: int | None = None


@dataclass(frozen=True)
class GroupProgress:
    group_id: str
    kind: GroupKind
    members: tuple[RunProgress, ...]
    attempts_used: int
    attempt_limit: int
    attempts_remaining: int
    snapshot_id: str | None
    replayed: bool = False
    identities: tuple[MemberIdentity, ...] = ()
    initial_requests: int = 0
    independent_case_count: int = 0
    algorithm: str | None = None
    seed: int | None = None

    @property
    def exit_code(self) -> Literal[0, 3, 4]:
        codes = {member.exit_code for member in self.members}
        return 4 if 4 in codes else 3 if 3 in codes else 0


def request_identity(
    case_id: str, input_hash: str, request: CompiledRequest | None
) -> RequestIdentity:
    return RequestIdentity(
        case_id,
        input_hash,
        request.body_hash if request else None,
        request.compiler if request else None,
        request.compiler_version if request else None,
        request.requested_model if request else None,
        request.semantic_headers_source if request else None,
    )
