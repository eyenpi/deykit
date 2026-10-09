"""Secret-safe provider configuration and authored fixture transport records."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from deykit.contracts.identities import ContentHash, ResourceId

from .common import CountText, ETag, Mutation, ResponseRecord


class ProviderProfileRequest(Mutation):
    profile_id: ResourceId
    adapter: ResourceId
    requested_model: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    destination: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    credential_ref: str | None = None
    expected_etag: ETag | None = None


class ProviderETagRequest(Mutation):
    expected_etag: ETag


class EnvironmentCredentialRequest(ProviderETagRequest):
    environment_name: Annotated[
        str, StringConstraints(min_length=1, max_length=256, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    ]


class OSCredentialRequest(ProviderETagRequest):
    credential_value: Annotated[str, StringConstraints(min_length=1, max_length=65536)]


class ProviderProfileDTO(ResponseRecord):
    id: ResourceId
    adapter: ResourceId
    requested_model: str
    destination: str
    etag: ETag
    compiler_id: ResourceId
    compiler_version: str
    input_kinds: tuple[Literal["text", "json"], ...]
    question_kind: Literal["choice"]
    max_options: int
    evidence_mode: Literal["authored_fixture", "live"]
    credential_configured: bool
    credential_kind: Literal["env", "keyring"] | None


class ProviderPageDTO(ResponseRecord):
    items: tuple[ProviderProfileDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class ProviderMutationDTO(ResponseRecord):
    operation_id: ResourceId
    replayed: bool
    profile: ProviderProfileDTO


class CredentialStatusDTO(ResponseRecord):
    profile_id: ResourceId
    configured: bool
    available: bool
    kind: Literal["env", "keyring"] | None


class ModelDTO(ResponseRecord):
    name: str
    description: str
    release_date: str


class ModelListDTO(ResponseRecord):
    profile_id: ResourceId
    network_check: Literal[True]
    inference_calls: Literal[0]
    models: tuple[ModelDTO, ...]


class FixtureCreateRequest(Mutation):
    fixture_set_id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    name: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    model_identity: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    binding_sources: tuple[str, ...] = Field(min_length=1, max_length=10000)
    note: str = ""

    @field_validator("binding_sources", mode="before")
    @classmethod
    def json_binding_sources(cls, value: object) -> object:
        return tuple(value) if type(value) is list else value


class FixtureBindingDTO(ResponseRecord):
    id: ResourceId
    case_id: ResourceId
    compiler: str
    compiler_version: str
    model_identity: str
    request_hash: ContentHash
    answer_question_id: ResourceId | None
    answer_option_id: ResourceId | None
    error_code: str | None
    error_reason: str | None


class FixtureSummaryDTO(ResponseRecord):
    id: ResourceId
    decision_id: ResourceId
    dataset_id: ResourceId
    name: str
    model_identity: str
    binding_count: CountText
    created_at: str
    content_hash: ContentHash
    bindings: tuple[FixtureBindingDTO, ...]
    requests: tuple[str, ...]
    etag: ETag | None = None


class FixturePageDTO(ResponseRecord):
    items: tuple[FixtureSummaryDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class FixtureCreatedDTO(ResponseRecord):
    operation_id: ResourceId
    replayed: bool
    fixture: FixtureSummaryDTO
