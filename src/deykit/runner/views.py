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
    cases: tuple[CaseProgress, ...]
    attempts: tuple[AttemptProgress, ...]
    segment_ids: tuple[str, ...]
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
        active,
        history.used,
        history.cap,
        max(0, history.cap - history.used),
        history.manifest.settings,
        tuple(
            CaseProgress(item.case_id, item.status, item.attempt_id, item.error)
            for item in history.results()
        ),
        tuple(attempts),
        tuple(segment.id for segment in history.segments),
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
