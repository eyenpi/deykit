"""Transport records for frozen results, evaluations and annotations."""

from typing import Literal

from pydantic import Field

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId

from .common import CountText, Mutation, ResponseRecord


class ResultRowDTO(FrozenModel):
    source: dict[str, object]


class ResultPageDTO(ResponseRecord):
    run_id: ResourceId
    result_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    evaluation_id: ResourceId | None
    selected_count: CountText
    status_counts: dict[str, CountText]
    summary: dict[str, object]
    filtered_count: CountText
    items: tuple[ResultRowDTO, ...]
    next_cursor: ResourceId | None


class CaseDetailDTO(ResponseRecord):
    source: dict[str, object]


class EvaluationDTO(ResponseRecord):
    evaluation_id: ResourceId
    run_id: ResourceId
    result_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    mode: Literal["original", "saved_answer_reevaluation"]
    metrics_source: str
    metrics: dict[str, object]
    content_hash: ContentHash
    created_at: str
    execution_operation_id: ResourceId | None
    replayed: bool


class EvaluationPageDTO(FrozenModel):
    items: tuple[EvaluationDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class EvaluateRequest(Mutation):
    result_snapshot_id: ResourceId
    label_snapshot_id: ResourceId | None = None
    mode: Literal["original", "saved_answer_reevaluation"] = "original"


class ReevaluateRequest(Mutation):
    result_snapshot_id: ResourceId


class AnnotationDTO(ResponseRecord):
    annotation_id: ResourceId
    run_id: ResourceId
    case_id: ResourceId
    note: str
    content_hash: ContentHash
    created_at: str
    replayed: bool


class AnnotationPageDTO(FrozenModel):
    items: tuple[AnnotationDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class AddAnnotationRequest(Mutation):
    case_id: ResourceId
    note: str = Field(min_length=1, max_length=16_384)
