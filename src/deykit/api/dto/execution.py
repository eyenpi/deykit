"""Reviewed run and execution-group preview transport records."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from deykit.application.checks import CheckRequest
from deykit.contracts.base import FrozenModel
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.ports import Collection
from deykit.contracts.records import ExecutionSettings
from deykit.runner.planner import RunRequest

from .common import CountText, ErrorDTO, Mutation, ResponseRecord, VersionRequest
from .data import SeedText

HttpPositiveInt = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
HttpDeadline = Annotated[int, Field(strict=True, ge=1, le=86_400)]
HttpRetryCount = Annotated[int, Field(strict=True, ge=0, le=1)]


class ExecutionSettingsRequestDTO(ExecutionSettings):
    max_attempts: HttpPositiveInt = 100
    concurrency: HttpPositiveInt = 2
    timeout_seconds: HttpPositiveInt = 60
    deadline_seconds: HttpDeadline = 600
    max_retries_per_case: HttpRetryCount = 1

    def to_application(self) -> ExecutionSettings:
        return ExecutionSettings(**self.model_dump())


class ExecutionSettingsViewDTO(FrozenModel):
    max_attempts: CountText
    concurrency: CountText
    timeout_seconds: CountText
    deadline_seconds: CountText
    max_retries_per_case: CountText

    @classmethod
    def from_application(cls, value: ExecutionSettings) -> ExecutionSettingsViewDTO:
        return cls(
            max_attempts=str(value.max_attempts),
            concurrency=str(value.concurrency),
            timeout_seconds=str(value.timeout_seconds),
            deadline_seconds=str(value.deadline_seconds),
            max_retries_per_case=str(value.max_retries_per_case),
        )


class RunRequestDTO(RunRequest):
    settings: ExecutionSettingsRequestDTO = ExecutionSettingsRequestDTO()

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
            settings=self.settings.to_application(),
        )


class StartRunRequest(VersionRequest):
    operation_id: ResourceId
    expected_review_context_hash: ContentHash
    request: RunRequestDTO


class CheckRequestDTO(CheckRequest):
    settings: ExecutionSettingsRequestDTO = ExecutionSettingsRequestDTO()

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
            settings=self.settings.to_application(),
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


class StartChoiceOrderRequest(VersionRequest):
    operation_id: ResourceId
    expected_review_context_hash: ContentHash
    request: ChoiceOrderRequestDTO


class StartCheckRequest(VersionRequest):
    operation_id: ResourceId
    expected_review_context_hash: ContentHash
    request: CheckRequestDTO


class ChoiceOrderPreviewRequest(VersionRequest):
    request: ChoiceOrderRequestDTO


class CheckPreviewRequest(VersionRequest):
    request: CheckRequestDTO


class ReviewSourceRecordDTO(FrozenModel):
    collection: Collection
    scope: tuple[ResourceId, ...]
    resource_id: ResourceId
    etag: ContentHash
    body_hash: ContentHash


class RunReviewContextDTO(ResponseRecord):
    definition_source: Literal["draft", "revision"]
    revision_id: ResourceId | None
    definition_hash: ContentHash
    source_context_hash: ContentHash
    provider_id: ResourceId
    destination: str
    adapter: str
    requested_model: str
    compiler_id: str
    compiler_version: str
    fixture_set_id: ResourceId | None
    source_records: tuple[ReviewSourceRecordDTO, ...]
    development_case_ids: tuple[ResourceId, ...]
    development_label_count: CountText


class RunCaseReviewDTO(FrozenModel):
    case_id: ResourceId
    input_hash: ContentHash
    request_hash: ContentHash | None
    compiler: str | None
    compiler_version: str | None
    requested_model: str | None
    input_error: ServiceError | None
    request_source: str | None
    request_source_redacted: bool | None
    semantic_headers_source: str | None = None


class RunPreviewSummaryDTO(ResponseRecord):
    decision_id: ResourceId
    dataset_id: ResourceId
    mode: Literal["fixture", "live"]
    provider_id: ResourceId
    fixture_set_id: ResourceId | None
    requested_model: str
    selected_case_ids: tuple[ResourceId, ...]
    initial_requests: CountText
    invalid_cases: tuple[ServiceError, ...]
    settings: ExecutionSettingsViewDTO
    development_case_count: CountText
    review_context_hash: ContentHash
    dry_run: bool
    semantic_headers_sources: tuple[str, ...] = ()


class RunPreviewDTO(RunPreviewSummaryDTO):
    review_context: RunReviewContextDTO
    case_reviews: tuple[RunCaseReviewDTO, ...]


class RequestIdentityDTO(ResponseRecord):
    case_id: ResourceId
    input_hash: ContentHash
    request_hash: ContentHash | None
    compiler: str | None
    compiler_version: str | None
    requested_model: str | None
    semantic_headers_source: str | None = None


class MemberIdentityDTO(ResponseRecord):
    option_order: tuple[ResourceId, ...] | None
    requests: tuple[RequestIdentityDTO, ...]
    run_id: ResourceId | None


class GroupMemberPreviewDTO(ResponseRecord):
    preview: RunPreviewSummaryDTO
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


class RunAcceptedDTO(ResponseRecord):
    operation_id: ResourceId
    run_id: ResourceId
    mode: Literal["fixture", "live"]
    replayed: bool
    segment_id: ResourceId | None
    progress_path: str


class GroupAcceptedDTO(ResponseRecord):
    operation_id: ResourceId
    group_id: ResourceId
    kind: Literal["choice_order", "regression_check"]
    mode: Literal["fixture", "live"]
    replayed: bool
    segment_id: ResourceId
    member_run_ids: tuple[ResourceId, ...]
    progress_path: str


class RunCancelRequest(Mutation):
    pass


class RunResumeRequest(Mutation):
    retry_unknown: bool = False
    max_attempts: HttpPositiveInt | None = None


class GroupResumeRequest(Mutation):
    retry_unknown: bool = False


class GroupCancelRequest(Mutation):
    pass


class RunCaseProgressDTO(FrozenModel):
    case_id: ResourceId
    status: str
    attempt_id: ResourceId | None
    error: ErrorDTO | None


class RunAttemptProgressDTO(FrozenModel):
    attempt_id: ResourceId
    case_id: ResourceId
    number: Annotated[int, Field(strict=True, ge=1)]
    kind: str
    state: str
    duration_seconds: (
        Annotated[str, StringConstraints(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")] | None
    )


class RunSegmentProgressDTO(FrozenModel):
    segment_id: ResourceId
    started_at: str
    deadline_at: str
    ended_at: str | None
    retry_unknown: bool


class RunSourceReferencesDTO(FrozenModel):
    decision_revision_id: ResourceId
    dataset_snapshot_id: ResourceId
    label_snapshot_id: ResourceId
    development_dataset_snapshot_id: ResourceId
    development_label_snapshot_id: ResourceId
    provider_profile_id: ResourceId
    fixture_set_id: ResourceId | None
    option_order: tuple[ResourceId, ...] | None
    adapter: ResourceId | None = None
    compiler_version: str | None = None
    compiler_id: ResourceId | None = None
    compiler_id_unavailable_reason: (
        Literal[
            "no_prepared_request",
            "prepared_compiler_mismatch",
            "inconsistent_prepared_compiler_identity",
        ]
        | None
    ) = None
    evidence_mode: Literal["authored_fixture", "live"] | None = None


class RunProgressDTO(ResponseRecord):
    run_id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    mode: Literal["fixture", "live"]
    requested_model: str
    state: str
    execution_active: bool
    attempts_used: CountText
    attempt_limit: CountText
    attempts_remaining: CountText
    settings: ExecutionSettingsViewDTO
    sources: RunSourceReferencesDTO
    cases: tuple[RunCaseProgressDTO, ...]
    attempts: tuple[RunAttemptProgressDTO, ...]
    segment_ids: tuple[ResourceId, ...]
    segments: tuple[RunSegmentProgressDTO, ...]
    result_snapshot_ids: tuple[ResourceId, ...]
    latest_result_snapshot_id: ResourceId | None
    replayed: bool
    execution_group_id: ResourceId | None
    group_attempts_remaining: CountText | None
    reason: ErrorDTO | None


class RunPageDTO(FrozenModel):
    items: tuple[RunProgressDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class GroupProgressDTO(ResponseRecord):
    group_id: ResourceId
    kind: Literal["choice_order", "regression_check"]
    members: tuple[RunProgressDTO, ...]
    attempts_used: CountText
    attempt_limit: CountText
    attempts_remaining: CountText
    snapshot_id: ResourceId | None
    replayed: bool
    initial_requests: CountText
    independent_case_count: CountText
    algorithm: str | None
    seed: Annotated[str, StringConstraints(pattern=r"^(?:0|-?[1-9][0-9]*)$")] | None


class RunResumePreviewDTO(ResponseRecord):
    run: RunProgressDTO
    planned_case_ids: tuple[ResourceId, ...]
    retry_unknown: bool
    proposed_attempt_limit: CountText
    dry_run: bool


class GroupMemberResumePreviewDTO(FrozenModel):
    run_id: ResourceId
    planned_case_ids: tuple[ResourceId, ...]


class GroupResumePreviewDTO(ResponseRecord):
    group: GroupProgressDTO
    segment_ids: tuple[ResourceId, ...]
    members: tuple[GroupMemberResumePreviewDTO, ...]
    retry_unknown: bool
    proposed_attempt_limit: CountText
    dry_run: bool
