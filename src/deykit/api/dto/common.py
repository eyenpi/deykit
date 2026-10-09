"""Transport primitives keep exact values outside JavaScript number semantics."""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field, StringConstraints, field_validator

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ContentHash, ResourceId

SafeInt = Annotated[int, Field(strict=True, ge=-9007199254740991, le=9007199254740991)]
Count = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
ExactIntegerText = Annotated[str, StringConstraints(strict=True, pattern=r"^(?:0|-?[1-9][0-9]*)$")]
CountText = Annotated[str, StringConstraints(strict=True, pattern=r"^(?:0|[1-9][0-9]*)$")]
ExactDecimalText = Annotated[
    str,
    StringConstraints(
        strict=True, pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
    ),
]
ETag = ContentHash
T = TypeVar("T")


class VersionRequest(FrozenModel):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("unsupported_schema_version")
        return value


class Mutation(VersionRequest):
    operation_id: ResourceId


class ResponseRecord(VersionRequest):
    schema_version: Literal[1] = 1


class ErrorDTO(ResponseRecord):
    code: str
    message: str
    resource_id: ResourceId | None = None
    row: Count | None = None
    reason: ResourceId | None = None
    correlation_id: ResourceId | None = None


class Success(ResponseRecord, Generic[T]):
    data: T
    warnings: tuple[ErrorDTO, ...] = ()


class Failure(ResponseRecord):
    error: ErrorDTO


class Versioned(FrozenModel, Generic[T]):
    record: T
    etag: ETag


class Page(FrozenModel, Generic[T]):
    items: tuple[T, ...]
    total: CountText
    next_cursor: ResourceId | None


class JsonSourceDTO(FrozenModel):
    source_text: str


class BootstrapRequest(VersionRequest):
    pass


class BootstrapReply(FrozenModel):
    capability: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]
    origin: str
    api_version: Literal[1] = 1
