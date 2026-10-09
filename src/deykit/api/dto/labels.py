"""Typed label review and history transport records."""

from typing import Literal

from pydantic import field_validator

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.records import CaseRecord, ChoiceDefinition, LabelChange, LabelRecord

from .common import CountText, Mutation, ResponseRecord


def _array_tuple(value: object) -> object:
    if type(value) is list:
        return tuple(_array_tuple(item) for item in value)
    return value


class LabelReviewDTO(FrozenModel):
    decision_id: ResourceId
    dataset_id: ResourceId
    case_id: ResourceId
    question_id: ResourceId
    input_hash: ContentHash
    decision_etag: ContentHash
    draft_etag: ContentHash
    label_etag: ContentHash | None


class LabelViewDTO(ResponseRecord):
    review: LabelReviewDTO
    case: CaseRecord
    definition: ChoiceDefinition
    label: LabelRecord | None
    reasons: tuple[Literal["disputed", "stale", "incompatible"], ...]
    missing_option_ids: tuple[ResourceId, ...]
    status: Literal["unlabelled", "excluded", "applicable"]


class LabelPageDTO(ResponseRecord):
    items: tuple[LabelViewDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class LabelEditDTO(FrozenModel):
    review: LabelReviewDTO
    action: Literal["set", "clear", "dispute", "resolve"]
    acceptable_option_ids: tuple[ResourceId, ...] = ()
    provenance: Literal[
        "human", "authored_fixture", "imported_unknown", "model_generated"
    ] | None = None
    note: str | None = None

    @field_validator("acceptable_option_ids", mode="before")
    @classmethod
    def json_array(cls, value: object) -> object:
        return _array_tuple(value)


class LabelBatchRequest(Mutation):
    edits: tuple[LabelEditDTO, ...]

    @field_validator("edits", mode="before")
    @classmethod
    def json_array(cls, value: object) -> object:
        return _array_tuple(value)


class LabelHistoryDTO(ResponseRecord):
    items: tuple[LabelChange, ...]


class LabelBatchDTO(ResponseRecord):
    changes: tuple[LabelChange, ...]
    replayed: bool
