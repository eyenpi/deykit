"""Reviewed run and execution-group preview transport records."""

from typing import Annotated, Literal

from pydantic import StringConstraints

from deykit.application.checks import CheckRequest
from deykit.application.diagnostics import ChoiceOrderRequest
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.records import ExecutionSettings
from deykit.runner.planner import RunRequest

from .common import CountText, ResponseRecord, VersionRequest


class RunPreviewRequest(VersionRequest):
    request: RunRequest


class ChoiceOrderPreviewRequest(VersionRequest):
    request: ChoiceOrderRequest


class CheckPreviewRequest(VersionRequest):
    request: CheckRequest


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
