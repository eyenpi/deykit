"""Frozen regression checks, with explicit expectation failures separate from run errors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Self, cast

from pydantic import model_validator

from deykit.application.dataset_support import decoded, fail, validated_model
from deykit.application.evaluations import FrozenEvaluation, frozen_evaluation_from_records
from deykit.application.execution import ExecutionService
from deykit.application.execution_groups import GroupExecutionService
from deykit.application.regressions import visible_regressions
from deykit.contracts.base import FrozenModel
from deykit.contracts.execution_groups import CheckSnapshot, ExecutionGroup, ExecutionGroupSegment
from deykit.contracts.identities import ResourceId
from deykit.contracts.json_value import JsonValue, dump_json
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.records import ExecutionSettings, RegressionRecord
from deykit.contracts.redaction import Sanitizer
from deykit.regressions.evidence import admit_regression_origin, frozen_case
from deykit.runner.group_evidence import admit_group_snapshots, group_budget
from deykit.runner.group_models import (
    GroupAcknowledged,
    GroupPlan,
    GroupPreview,
    GroupProgress,
    GroupResumePreview,
)
from deykit.runner.planner import RunRequest
from deykit.runner.review import regression_membership_records


class CheckRequest(FrozenModel):
    decision_id: ResourceId
    mode: Literal["fixture", "live"]
    provider_id: ResourceId | None = None
    fixture_set_id: ResourceId | None = None
    revision_id: ResourceId | None = None
    regression_ids: tuple[ResourceId, ...] = ()
    settings: ExecutionSettings = ExecutionSettings()

    @model_validator(mode="after")
    def explicit_selection(self) -> Self:
        if self.mode == "fixture" and self.fixture_set_id is None:
            raise ValueError("fixture_set_required")
        if self.mode == "live" and (self.provider_id is None or self.fixture_set_id is not None):
            raise ValueError("live_profile_required")
        if len(set(self.regression_ids)) != len(self.regression_ids):
            raise ValueError("duplicate_regression_selection")
        if self.settings.timeout_seconds > 600 or self.settings.concurrency > 64:
            raise ValueError("execution_resource_limit")
        return self


@dataclass(frozen=True)
class CheckCase:
    regression_id: str
    dataset_id: str
    case_id: str
    run_id: str
    result_snapshot_id: str
    status: str
    expected_option_ids: tuple[str, ...]
    actual_option_id: str | None
    passed: bool | None
    provenance: str = ""
    original_split: str = ""
    input_hash: str = ""
    source_run_id: str | None = None
    source_result_snapshot_id: str | None = None
    source_attempt_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class CheckView:
    group: GroupProgress
    cases: tuple[CheckCase, ...]
    expectation_failures: int
    baseline_unavailable: Literal["frozen_regression_selection"] = "frozen_regression_selection"

    @property
    def exit_code(self) -> Literal[0, 3, 4, 5]:
        if self.group.exit_code:
            return self.group.exit_code
        return 5 if self.expectation_failures else 0


class CheckService:
    def __init__(self, execution: ExecutionService) -> None:
        self.execution = execution
        self.groups = GroupExecutionService(execution)

    def _plan(self, request: CheckRequest) -> GroupPlan:
        if len(set(request.regression_ids)) != len(request.regression_ids):
            fail("duplicate_regression_selection", "preflight_failed")
        with self.execution.source.consistent_read():
            captured = self.execution.source.capture_snapshot()
            visible = visible_regressions(captured, request.decision_id)
            by_id = {r.id: r for r in visible}
            ids = request.regression_ids or tuple(by_id)
            if not ids:
                fail("empty_regression_scope", "preflight_failed")
            if any(key not in by_id for key in ids):
                fail("regression_not_visible", "preflight_failed")
            datasets: dict[str, list[str]] = {}
            for key in ids:
                frozen_case(by_id[key])
                datasets.setdefault(by_id[key].dataset_id, []).append(key)
            selections = tuple(
                RunRequest(
                    decision_id=request.decision_id,
                    dataset_id=dataset_id,
                    mode=request.mode,
                    provider_id=request.provider_id,
                    fixture_set_id=request.fixture_set_id,
                    revision_id=request.revision_id,
                    regression_ids=tuple(regressions),
                    settings=request.settings,
                )
                for dataset_id, regressions in sorted(datasets.items())
            )
            plans = self.execution.planner.prepare_many(selections, captured=captured)
        return GroupPlan(
            "regression_check",
            plans,
            request.settings.max_attempts,
            request.settings.deadline_seconds,
            tuple(by_id) if not request.regression_ids else None,
            review_membership_records=regression_membership_records(
                captured,
                request.decision_id,
                request.regression_ids if request.regression_ids else None,
            ),
        )

    @staticmethod
    def _selection_source(request: CheckRequest) -> str:
        return dump_json(
            {
                "kind": "regression_check",
                "request": cast(JsonValue, request.model_dump(mode="json")),
            }
        )

    def preview(self, request: CheckRequest) -> GroupPreview:
        request = validated_model(CheckRequest, request, "invalid_check_request")
        return self.groups.preview(
            lambda: self._plan(request),
            selection_source=self._selection_source(request),
        )

    async def start(
        self,
        request: CheckRequest,
        *,
        operation_id: str,
        expected_review_context_hash: str | None = None,
        on_created: Callable[[GroupAcknowledged], None] | None = None,
    ) -> CheckView:
        request = validated_model(CheckRequest, request, "invalid_check_request")
        progress = await self.groups.start(
            selection_source=self._selection_source(request),
            prepare=lambda: self._plan(request),
            operation_id=operation_id,
            expected_review_context_hash=expected_review_context_hash,
            on_created=on_created,
        )
        return self._view(progress)

    async def resume(
        self,
        group_id: str,
        *,
        operation_id: str,
        retry_unknown: bool = False,
        on_resumed: Callable[[GroupAcknowledged], None] | None = None,
    ) -> CheckView:
        return self._view(
            await self.groups.resume(
                group_id,
                operation_id=operation_id,
                retry_unknown=retry_unknown,
                expected_kind="regression_check",
                on_resumed=on_resumed,
            )
        )

    def preview_resume(
        self, group_id: str, *, retry_unknown: bool = False
    ) -> GroupResumePreview:
        return self.groups.preview_resume(
            group_id, retry_unknown=retry_unknown, expected_kind="regression_check"
        )

    def cancel(self, group_id: str, *, operation_id: str) -> GroupProgress:
        return self.groups.cancel(
            group_id, operation_id=operation_id, expected_kind="regression_check"
        )

    def read(self, group_id: str) -> CheckView:
        return self._view(self.groups.show(group_id))

    def _view(self, progress: GroupProgress) -> CheckView:
        if progress.kind != "regression_check":
            fail("regression_check_group_required")
        if progress.snapshot_id is None:
            return CheckView(progress, (), 0)
        with self.execution.source.consistent_read():
            records = self.execution.source.capture_snapshot()
        progress = self.groups.captured_progress(
            records,
            progress.group_id,
            active=any(m.execution_active for m in progress.members),
            replayed=progress.replayed,
        )
        if progress.snapshot_id is None:
            fail("group_snapshot_missing", "incompatible_data")
        frozen = check_snapshot_from_records(records, progress.snapshot_id)
        return CheckView(progress, frozen.cases, frozen.expectation_failures)


@dataclass(frozen=True)
class FrozenCheckSnapshot:
    group: ExecutionGroup
    segment: ExecutionGroupSegment | None
    snapshot: CheckSnapshot
    members: tuple[FrozenEvaluation, ...]
    regressions: tuple[RegressionRecord, ...]
    cases: tuple[CheckCase, ...]
    expectation_failures: int
    baseline_unavailable: Literal["frozen_regression_selection"]


def check_snapshot_from_records(
    records: tuple[StoredRecord, ...], snapshot_id: str
) -> FrozenCheckSnapshot:
    """Read an exact check boundary without selection visibility or recovery side effects."""
    index = {r.key: r for r in records}
    if len(index) != len(records):
        fail("duplicate_captured_key", "incompatible_data")
    stored = index.get(ResourceKey("check_snapshots", snapshot_id))
    if stored is None:
        fail("check_snapshot_missing", "incompatible_data")
    snapshot = decoded(CheckSnapshot, stored)
    budget = group_budget(records, snapshot.group_id)
    if (
        snapshot not in admit_group_snapshots(records, snapshot.group_id)
        or budget.group.kind != "regression_check"
    ):
        fail("check_snapshot_mismatch", "incompatible_data")
    members = tuple(
        frozen_evaluation_from_records(records, r.run_id, r.result_snapshot_id, None, "original")
        for r in snapshot.results
    )
    cases: list[CheckCase] = []
    regressions: list[RegressionRecord] = []
    for frozen in members:
        result_by_case = {r.case_id: r for r in frozen.results.results}
        for key in frozen.manifest.regression_ids:
            stored = index.get(ResourceKey("regressions", key))
            if stored is None:
                fail("check_regression_missing", "incompatible_data")
            regression = decoded(RegressionRecord, stored)
            case = admit_regression_origin(records, regression)
            result = result_by_case.get(case.id)
            if (
                result is None
                or result.input_hash != regression.input_hash
                or regression.decision_id != frozen.manifest.decision_id
                or regression.dataset_id != frozen.manifest.dataset_id
                or regression.question_id != frozen.revision.definition.questions[0].id
                or case not in frozen.dataset.cases
                or not set(regression.acceptable_option_ids).issubset(
                    o.id for o in frozen.revision.definition.questions[0].options
                )
            ):
                fail("check_regression_mismatch", "incompatible_data")
            actual = result.answer.option_id if result.answer else None
            regressions.append(regression)
            cases.append(
                CheckCase(
                    key,
                    regression.dataset_id,
                    case.id,
                    frozen.manifest.id,
                    frozen.results.id,
                    result.status,
                    regression.acceptable_option_ids,
                    actual,
                    actual in regression.acceptable_option_ids if actual else None,
                    regression.provenance or "",
                    case.split,
                    regression.input_hash,
                    regression.source_run_id,
                    regression.source_result_snapshot_id,
                    regression.source_attempt_id,
                    Sanitizer().text(regression.reason),
                )
            )
    return FrozenCheckSnapshot(
        budget.group,
        next((s for s in budget.segments if s.id == snapshot.segment_id), None),
        snapshot,
        members,
        tuple(regressions),
        tuple(cases),
        sum(c.passed is False for c in cases),
        "frozen_regression_selection",
    )
