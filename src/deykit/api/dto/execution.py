"""Reviewed run and execution-group preview transport records."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from deykit.application.checks import CheckRequest
from deykit.contracts.base import FrozenModel
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.records import ExecutionSettings
from deykit.runner.planner import RunRequest

from .common import CountText, ResponseRecord, VersionRequest
from .data import SeedText


class RunRequestDTO(RunRequest):
    @field_validator("case_ids", "option_order", "regression_ids", mode="before")
    @classmethod
    def json_arrays(cls, value: object) -> object:
        return tuple(value) if type(value) is list else value

    def to_application(self) -> RunRequest:
        return RunRequest(
            decision_id=self.decision_id,
            dataset_id=self.dataset_id,
            mode=self.mode,
            provider_id=self.provider_id,
            fixture_set_id=self.fixture_set_id,
            revision_id=self.revision_id,
            split=self.split,
            case_ids=self.case_ids,
            option_order=self.option_order,
            regression_ids=self.regression_ids,
            settings=self.settings,
        )


class CheckRequestDTO(CheckRequest):
    @field_validator("regression_ids", mode="before")
    @classmethod
    def json_regression_ids(cls, value: object) -> object:
        return tuple(value) if type(value) is list else value

    def to_application(self) -> CheckRequest:
        return CheckRequest(
            decision_id=self.decision_id,
            mode=self.mode,
            provider_id=self.provider_id,
            fixture_set_id=self.fixture_set_id,
            revision_id=self.revision_id,
            regression_ids=self.regression_ids,
            settings=self.settings,
        )


class RunPreviewRequest(VersionRequest):
    request: RunRequestDTO


class ChoiceOrderRequestDTO(FrozenModel):
    run: RunRequestDTO
    orders: Annotated[int, Field(ge=1, le=4)] = 4
    seed: SeedText = "0"

    @field_validator("seed")
    @classmethod
    def signed_64_bit_seed(cls, value: str) -> str:
        if len(value) > 20 or not -(2**63) <= int(value) < 2**63:
            raise ValueError("invalid_choice_order_seed")
        return value


class ChoiceOrderPreviewRequest(VersionRequest):
    request: ChoiceOrderRequestDTO


class CheckPreviewRequest(VersionRequest):
    request: CheckRequestDTO


class RunPreviewDTO(ResponseRecord):
    decision_id: ResourceId
    dataset_id: ResourceId
    mode: Literal["fixture", "live"]
    provider_id: ResourceId
    fixture_set_id: ResourceId | None
    requested_model: str
    selected_case_ids: tuple[ResourceId, ...]
    initial_requests: CountText
    invalid_cases: tuple[ServiceError, ...]
    settings: ExecutionSettings
    development_case_count: CountText
    review_context_hash: ContentHash
    dry_run: bool


class RequestIdentityDTO(ResponseRecord):
    case_id: ResourceId
    input_hash: ContentHash
    request_hash: ContentHash | None
    compiler: str | None
    compiler_version: str | None
    requested_model: str | None


class MemberIdentityDTO(ResponseRecord):
    option_order: tuple[ResourceId, ...] | None
    requests: tuple[RequestIdentityDTO, ...]
    run_id: ResourceId | None


class GroupMemberPreviewDTO(ResponseRecord):
    preview: RunPreviewDTO
    identity: MemberIdentityDTO


class GroupPreviewDTO(ResponseRecord):
    kind: Literal["choice_order", "regression_check"]
    members: tuple[GroupMemberPreviewDTO, ...]
    initial_requests: CountText
    attempt_limit: CountText
    deadline_seconds: CountText
    review_context_hash: ContentHash
    dry_run: bool
    independent_case_count: CountText
    algorithm: str | None
    seed: Annotated[str, StringConstraints(pattern=r"^(?:0|-?[1-9][0-9]*)$")] | None
