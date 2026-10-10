"""Transport records for saved immutable reports."""

from typing import Literal

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.reports.models import RawChoices, ReportRequest, ReportTargetKind

from .common import CountText, Mutation, ResponseRecord


class CreateReportRequest(Mutation):
    target_id: ResourceId
    target_kind: ReportTargetKind | None = None
    evaluation_id: ResourceId | None = None
    result_snapshot_id: ResourceId | None = None
    group_snapshot_id: ResourceId | None = None
    raw: RawChoices = RawChoices()

    def to_application(self) -> ReportRequest:
        return ReportRequest(
            target_id=self.target_id,
            target_kind=self.target_kind,
            evaluation_id=self.evaluation_id,
            result_snapshot_id=self.result_snapshot_id,
            group_snapshot_id=self.group_snapshot_id,
            raw=self.raw,
        )


class ReportDTO(ResponseRecord):
    report_id: ResourceId
    content_hash: ContentHash
    created_at: str
    target_id: ResourceId | None
    target_kind: Literal["run", "evaluation", "comparison", "diagnostic", "check"] | None
    raw: RawChoices
    evaluation_ids: tuple[ResourceId, ...]
    result_snapshot_ids: tuple[ResourceId, ...]
    label_snapshot_ids: tuple[ResourceId, ...]
    comparison_id: ResourceId | None
    diagnostic_snapshot_id: ResourceId | None
    check_snapshot_id: ResourceId | None
    evidence_modes: tuple[str, ...]
    legacy: bool
    nonexportable_reason: str | None


class ReportPageDTO(FrozenModel):
    items: tuple[ReportDTO, ...]
    total: CountText
    next_cursor: ResourceId | None
