"""Safe command/API views; raw inputs, requests and responses never appear here."""

from dataclasses import dataclass
from typing import Literal

from deykit.contracts.errors import ServiceError
from deykit.contracts.records import ExecutionSettings
from deykit.runner.history import RunHistory
from deykit.runner.planner import RunPlan


@dataclass(frozen=True)
class RunCreated:
    run_id: str
    mode: Literal["fixture", "live"]
    replayed: bool


@dataclass(frozen=True)
class RunResumed:
    run_id: str
    segment_id: str
    mode: Literal["fixture", "live"]
    replayed: bool


@dataclass(frozen=True)
class CaseProgress:
    case_id: str
    status: str
    attempt_id: str | None
    error: ServiceError | None


@dataclass(frozen=True)
class AttemptProgress:
    attempt_id: str
    case_id: str
    number: int
    kind: str
    state: str
    duration_seconds: float | None


@dataclass(frozen=True)
class SegmentProgress:
    segment_id: str
    started_at: str
    deadline_at: str
    ended_at: str | None
    retry_unknown: bool


@dataclass(frozen=True)
class RunSourceReferences:
    decision_revision_id: str
    dataset_snapshot_id: str
    label_snapshot_id: str
    development_dataset_snapshot_id: str
    development_label_snapshot_id: str
    provider_profile_id: str
    fixture_set_id: str | None
    option_order: tuple[str, ...] | None


@dataclass(frozen=True)
class RunProgress:
    run_id: str
    decision_id: str
    dataset_id: str
    mode: Literal["fixture", "live"]
    requested_model: str
    state: str
    execution_active: bool
    attempts_used: int
    attempt_limit: int
    attempts_remaining: int
    settings: ExecutionSettings
    sources: RunSourceReferences
    cases: tuple[CaseProgress, ...]
    attempts: tuple[AttemptProgress, ...]
    segment_ids: tuple[str, ...]
    segments: tuple[SegmentProgress, ...]
    result_snapshot_ids: tuple[str, ...]
    latest_result_snapshot_id: str | None
    replayed: bool = False

    @property
    def exit_code(self) -> Literal[0, 3, 4]:
        if self.state in {"cancelled", "interrupted", "budget_exhausted", "cancelling"} or any(
            case.status in {"pending", "unknown"} for case in self.cases
        ):
            return 4
        if any(case.status in {"input_invalid", "response_error"} for case in self.cases):
            return 3
        return 0


@dataclass(frozen=True)
class RunPreview:
    decision_id: str
    dataset_id: str
    mode: Literal["fixture", "live"]
    provider_id: str
    fixture_set_id: str | None
    requested_model: str
    selected_case_ids: tuple[str, ...]
    initial_requests: int
    invalid_cases: tuple[ServiceError, ...]
    settings: ExecutionSettings
    development_case_count: int
    dry_run: bool = True


def preview_view(plan: RunPlan) -> RunPreview:
    return RunPreview(
        plan.selection.decision_id,
        plan.selection.dataset_id,
        plan.selection.mode,
        plan.provider.id,
        plan.selection.fixture_set_id,
        plan.provider.requested_model,
        tuple(case.id for case in plan.cases),
        plan.initial_requests,
        tuple(item.error for item in plan.prepared if item.error),
        plan.selection.settings,
        len(plan.development_cases),
    )


def progress_view(
    history: RunHistory, *, active: bool = False, replayed: bool = False
) -> RunProgress:
    attempts: list[AttemptProgress] = []
    for attempt in history.attempts:
        event = history.final_event(attempt.id)
        attempts.append(
            AttemptProgress(
                attempt.id,
                attempt.case_id,
                attempt.number,
                attempt.kind,
                event.state if event else "reserved",
                event.duration_seconds if event else None,
            )
        )
    return RunProgress(
        history.manifest.id,
        history.manifest.decision_id or "",
        history.manifest.dataset_id or "",
        history.manifest.mode,
        history.manifest.requested_model,
        history.state,
        active and history.state in {"preparing", "running", "cancelling"},
        history.used,
        history.cap,
        max(0, history.cap - history.used),
        history.manifest.settings,
        RunSourceReferences(
            history.manifest.decision_revision_id,
            history.manifest.dataset_snapshot_id,
            history.manifest.label_snapshot_id,
            history.manifest.baseline_dataset_snapshot_id or "",
            history.manifest.baseline_label_snapshot_id or "",
            history.manifest.provider_profile_id,
            history.manifest.fixture_set_id,
            history.manifest.option_order,
        ),
        tuple(
            CaseProgress(item.case_id, item.status, item.attempt_id, item.error)
            for item in history.results()
        ),
        tuple(attempts),
        tuple(segment.id for segment in history.segments),
        tuple(
            SegmentProgress(
                segment.id,
                segment.started_at,
                segment.deadline_at,
                next(
                    (
                        event.created_at
                        for event in reversed(history.events)
                        if event.segment_id == segment.id
                        and event.state
                        in {
                            "completed",
                            "completed_with_errors",
                            "cancelled",
                            "interrupted",
                            "budget_exhausted",
                        }
                    ),
                    None,
                ),
                segment.retry_unknown,
            )
            for segment in history.segments
        ),
        tuple(snapshot.id for snapshot in history.snapshots),
        history.snapshots[-1].id if history.snapshots else None,
        replayed,
    )


@dataclass(frozen=True)
class ResumePreview:
    run: RunProgress
    planned_case_ids: tuple[str, ...]
    retry_unknown: bool
    proposed_attempt_limit: int
    dry_run: bool = True


@dataclass(frozen=True)
class RunPage:
    items: tuple[RunProgress, ...]
    total: int
    next_cursor: str | None
