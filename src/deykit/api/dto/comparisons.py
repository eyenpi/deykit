"""Transport records for saved evaluation comparisons."""

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId

from .common import CountText, Mutation, ResponseRecord


class CreateComparisonRequest(Mutation):
    left_evaluation_id: ResourceId
    right_evaluation_id: ResourceId


class ComparisonDTO(ResponseRecord):
    comparison_id: ResourceId
    left_evaluation_id: ResourceId
    right_evaluation_id: ResourceId
    left_result_snapshot_id: ResourceId
    right_result_snapshot_id: ResourceId
    outcomes: dict[str, object]
    content_hash: ContentHash
    created_at: str
    replayed: bool


class ComparisonPageDTO(FrozenModel):
    items: tuple[ComparisonDTO, ...]
    total: CountText
    next_cursor: ResourceId | None
