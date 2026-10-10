"""Transport records for explicit regression oracles."""

from typing import Literal

from pydantic import Field, field_validator

from deykit.application.regressions import RegressionAdd
from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId

from .common import Mutation, ResponseRecord


class AddRegressionRequest(Mutation):
    run_id: ResourceId
    case_id: ResourceId
    acceptable_option_ids: tuple[ResourceId, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    result_snapshot_id: ResourceId | None = None
    provenance: Literal["human", "authored_fixture", "imported_unknown", "model_generated"] = (
        "human"
    )

    @field_validator("acceptable_option_ids", mode="before")
    @classmethod
    def json_array(cls, value: object) -> object:
        return tuple(value) if type(value) is list else value

    def to_application(self) -> RegressionAdd:
        return RegressionAdd(
            run_id=self.run_id,
            case_id=self.case_id,
            acceptable_option_ids=self.acceptable_option_ids,
            reason=self.reason,
            result_snapshot_id=self.result_snapshot_id,
            provenance=self.provenance,
        )


class RemoveRegressionRequest(Mutation):
    decision_id: ResourceId


class RegressionDTO(ResponseRecord):
    regression_id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    case_id: ResourceId
    question_id: ResourceId
    acceptable_option_ids: tuple[ResourceId, ...]
    reason: str
    original_split: str
    provenance: Literal["human", "authored_fixture", "imported_unknown", "model_generated"]
    source_run_id: ResourceId
    source_result_snapshot_id: ResourceId
    input_hash: ContentHash
    removed: bool
    executable: bool
    unavailable_reason: str | None


class RegressionPageDTO(FrozenModel):
    items: tuple[RegressionDTO, ...]
