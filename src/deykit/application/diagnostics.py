"""Choice-order diagnostics preserve original-case denominators and exact ordered plans."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Annotated, cast

from pydantic import Field

from deykit.application.dataset_support import fail, validated_model
from deykit.application.evaluations import FrozenEvaluation, frozen_evaluation_from_records
from deykit.application.execution import ExecutionService
from deykit.application.execution_groups import GroupExecutionService
from deykit.contracts.base import FrozenModel
from deykit.contracts.execution_groups import (
    DiagnosticSnapshot,
    ExecutionGroup,
    ExecutionGroupSegment,
)
from deykit.contracts.json_value import JsonValue, dump_json
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.diagnostics.summary import OrderSummary, summarize_orders
from deykit.runner.group_evidence import admit_group_snapshots, group_budget
from deykit.runner.group_models import (
    GroupAcknowledged,
    GroupPlan,
    GroupPreview,
    GroupProgress,
    GroupResumePreview,
)
from deykit.runner.planner import RunRequest


class ChoiceOrderRequest(FrozenModel):
    run: RunRequest
    orders: Annotated[int, Field(ge=1, le=4)] = 4
    seed: Annotated[int, Field(ge=-(2**63), lt=2**63)] = 0


@dataclass(frozen=True)
class DiagnosticView:
    group: GroupProgress
    summary: OrderSummary | None

    @property
    def exit_code(self) -> int:
        return self.group.exit_code


class DiagnosticService:
    def __init__(self, execution: ExecutionService) -> None:
        self.execution = execution
        self.groups = GroupExecutionService(execution)

    def _plan(self, request: ChoiceOrderRequest) -> GroupPlan:
        return GroupPlan(
            "choice_order",
            self.execution.planner.prepare_orders(
                request.run, orders=request.orders, seed=request.seed
            ),
            request.run.settings.max_attempts,
            request.run.settings.deadline_seconds,
            review_membership_records=(),
        )

    @staticmethod
    def _selection_source(request: ChoiceOrderRequest) -> str:
        return dump_json(
            {
                "kind": "choice_order",
                "request": cast(JsonValue, request.model_dump(mode="json")),
            }
        )

    def preview(self, request: ChoiceOrderRequest) -> GroupPreview:
        request = validated_model(ChoiceOrderRequest, request, "invalid_diagnostic_request")
        return replace(
            self.groups.preview(
                lambda: self._plan(request),
                selection_source=self._selection_source(request),
            ),
            algorithm="deykit-choice-order-v1",
            seed=request.seed,
        )

    async def start(
        self,
        request: ChoiceOrderRequest,
        *,
        operation_id: str,
        expected_review_context_hash: str | None = None,
        on_created: Callable[[GroupAcknowledged], None] | None = None,
    ) -> DiagnosticView:
        request = validated_model(ChoiceOrderRequest, request, "invalid_diagnostic_request")
        result = await self.groups.start(
            selection_source=self._selection_source(request),
            prepare=lambda: self._plan(request),
            operation_id=operation_id,
            expected_review_context_hash=expected_review_context_hash,
            on_created=on_created,
        )
        return self._view(result)

    async def resume(
        self,
        group_id: str,
        *,
        operation_id: str,
        retry_unknown: bool = False,
        on_resumed: Callable[[GroupAcknowledged], None] | None = None,
    ) -> DiagnosticView:
        return self._view(
            await self.groups.resume(
                group_id,
                operation_id=operation_id,
                retry_unknown=retry_unknown,
                expected_kind="choice_order",
                on_resumed=on_resumed,
            )
        )

    def preview_resume(self, group_id: str, *, retry_unknown: bool = False) -> GroupResumePreview:
        return self.groups.preview_resume(
            group_id, retry_unknown=retry_unknown, expected_kind="choice_order"
        )

    def cancel(self, group_id: str, *, operation_id: str) -> GroupProgress:
        return self.groups.cancel(group_id, operation_id=operation_id, expected_kind="choice_order")

    def read(self, group_id: str) -> DiagnosticView:
        return self._view(self.groups.show(group_id))

    def _view(self, progress: GroupProgress) -> DiagnosticView:
        if progress.kind != "choice_order":
            fail("diagnostic_group_required")
        if progress.snapshot_id is None:
            return DiagnosticView(progress, None)
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
        frozen = diagnostic_snapshot_from_records(records, progress.snapshot_id)
        return DiagnosticView(progress, frozen.summary)


@dataclass(frozen=True)
class FrozenDiagnosticSnapshot:
    group: ExecutionGroup
    segment: ExecutionGroupSegment | None
    snapshot: DiagnosticSnapshot
    members: tuple[FrozenEvaluation, ...]
    summary: OrderSummary


def diagnostic_snapshot_from_records(
    records: tuple[StoredRecord, ...], snapshot_id: str
) -> FrozenDiagnosticSnapshot:
    """Pure pinned admission; later progress never changes this immutable boundary."""
    stored = next(
        (r for r in records if r.key == ResourceKey("diagnostic_snapshots", snapshot_id)), None
    )
    if stored is None:
        fail("diagnostic_snapshot_missing", "incompatible_data")
    from deykit.application.dataset_support import decoded

    snapshot = decoded(DiagnosticSnapshot, stored)
    budget = group_budget(records, snapshot.group_id)
    if (
        snapshot not in admit_group_snapshots(records, snapshot.group_id)
        or budget.group.kind != "choice_order"
    ):
        fail("diagnostic_snapshot_mismatch", "incompatible_data")
    members = tuple(
        frozen_evaluation_from_records(records, r.run_id, r.result_snapshot_id, None, "original")
        for r in snapshot.results
    )
    first = members[0]
    if any(
        f.revision.definition != first.revision.definition or f.dataset.cases != first.dataset.cases
        for f in members
    ):
        fail("diagnostic_source_mismatch", "incompatible_data")
    summary = summarize_orders(
        first.revision.definition,
        first.manifest.case_ids,
        tuple(f.results.results for f in members),
    )
    return FrozenDiagnosticSnapshot(
        budget.group,
        next((s for s in budget.segments if s.id == snapshot.segment_id), None),
        snapshot,
        members,
        summary,
    )
