"""Project registration and recent-workspace transport records."""

from typing import Annotated, Literal

from pydantic import StringConstraints

from deykit.contracts.identities import ResourceId
from deykit.contracts.records import UtcTimestamp

from .common import CountText, ETag, Mutation, ResponseRecord, Success, VersionRequest


class ProjectRecordDTO(ResponseRecord):
    id: ResourceId
    name: Annotated[str, StringConstraints(min_length=1)]
    created_at: UtcTimestamp
    default_provider_id: ResourceId | None = None


class RecentProjectDTO(ResponseRecord):
    id: str
    name: str
    path: str
    last_opened_at: UtcTimestamp
    project_id: ResourceId


class RecentProjectsDTO(ResponseRecord):
    items: tuple[RecentProjectDTO, ...]


class RegisterProjectRequest(VersionRequest):
    operation_id: ResourceId
    action: Literal["open", "create"]
    path: Annotated[str, StringConstraints(min_length=1)]
    name: str | None = None


class RegistrationDTO(ResponseRecord):
    registration_id: ResourceId
    path: str
    project: ProjectRecordDTO
    project_etag: ETag
    execution_active: bool
    record_count: CountText
    demo: None = None


class RegistrationSuccess(Success[RegistrationDTO]):
    pass


class ResourceSummaryDTO(ResponseRecord):
    id: ResourceId
    name: str


class ProjectOverviewDTO(ResponseRecord):
    registration: RegistrationDTO
    decisions: tuple[ResourceSummaryDTO, ...]
    datasets: tuple[ResourceSummaryDTO, ...]


class RebuildIndexDTO(ResponseRecord):
    record_count: CountText


class DemoCreateRequest(Mutation):
    path: Annotated[str, StringConstraints(min_length=1)]


class DemoSummaryDTO(ResponseRecord):
    operation_id: ResourceId
    replayed: bool
    evidence_mode: Literal["authored_fixture"]
    project_id: ResourceId
    decision_id: ResourceId
    revision_id: ResourceId
    dataset_id: ResourceId
    profile_id: ResourceId
    fixture_set_id: ResourceId
    case_count: CountText
    binding_count: CountText
    label_count: CountText


class DemoCreateDTO(ResponseRecord):
    registration: RegistrationDTO
    demo: DemoSummaryDTO
