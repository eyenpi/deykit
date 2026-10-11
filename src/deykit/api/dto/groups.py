"""Public result records for shared diagnostic and regression-check groups."""

from typing import Literal

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId

from .common import CountText
from .execution import GroupProgressDTO


class DiagnosticViewDTO(FrozenModel):
    group: GroupProgressDTO
    summary: dict[str, object] | None
    exit_code: Literal[0, 3, 4]


class CheckViewDTO(FrozenModel):
    group: GroupProgressDTO
    cases: tuple[dict[str, object], ...]
    expectation_failures: CountText
    baseline_unavailable: Literal["frozen_regression_selection"]
    exit_code: Literal[0, 3, 4, 5]


class SnapshotResultDTO(FrozenModel):
    run_id: ResourceId
    result_snapshot_id: ResourceId


class SnapshotMetadataDTO(FrozenModel):
    id: ResourceId
    sequence: CountText
    group_id: ResourceId
    segment_id: ResourceId | None
    content_hash: ContentHash
    created_at: str
    results: tuple[SnapshotResultDTO, ...]


class FrozenMemberContextDTO(FrozenModel):
    run_id: ResourceId
    result_snapshot_id: ResourceId
    result_content_hash: ContentHash
    through_event_sequence: CountText
    label_snapshot_id: ResourceId
    label_content_hash: ContentHash
    decision_id: ResourceId
    dataset_id: ResourceId
    decision_revision_id: ResourceId
    decision_definition_hash: ContentHash
    dataset_snapshot_id: ResourceId
    dataset_content_hash: ContentHash


class DiagnosticSnapshotDetailDTO(FrozenModel):
    snapshot: SnapshotMetadataDTO
    members: tuple[FrozenMemberContextDTO, ...]
    summary: dict[str, object]


class CheckSnapshotCaseDTO(FrozenModel):
    regression_id: ResourceId
    dataset_id: ResourceId
    case_id: ResourceId
    run_id: ResourceId
    result_snapshot_id: ResourceId
    status: str
    expected_option_ids: tuple[ResourceId, ...]
    actual_option_id: ResourceId | None
    passed: bool | None
    provenance: str
    original_split: str
    input_hash: ContentHash
    source_run_id: ResourceId | None
    source_result_snapshot_id: ResourceId | None
    source_attempt_id: ResourceId | None
    reason: str


class CheckSnapshotDetailDTO(FrozenModel):
    snapshot: SnapshotMetadataDTO
    members: tuple[FrozenMemberContextDTO, ...]
    cases: tuple[CheckSnapshotCaseDTO, ...]
    expectation_failures: CountText
    baseline_unavailable: Literal["frozen_regression_selection"]
