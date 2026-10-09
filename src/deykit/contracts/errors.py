"""Safe service results independent of HTTP and terminal rendering."""

from typing import Generic, Literal, TypeVar

from deykit.contracts.base import Record
from deykit.contracts.identities import ResourceId
from deykit.contracts.selection import SelectionDetails

ErrorCode = Literal[
    "validation_error",
    "not_found",
    "conflict",
    "execution_locked",
    "incompatible_data",
    "preflight_failed",
    "provider_auth",
    "provider_rejected",
    "response_invalid",
    "missing_fixture",
    "run_incomplete",
    "expectation_failed",
    "internal_error",
]
_MESSAGES: dict[str, str] = {
    "validation_error": "The supplied data is invalid.",
    "not_found": "The requested resource was not found.",
    "conflict": "The resource changed; reload before saving.",
    "execution_locked": "Another execution owns this project.",
    "incompatible_data": "The selected evidence is incompatible.",
    "preflight_failed": "The execution could not pass preflight.",
    "provider_auth": "Provider authentication failed.",
    "provider_rejected": "The provider rejected the request.",
    "response_invalid": "The response is not a valid answer.",
    "missing_fixture": "No fixture matches the compiled request.",
    "run_incomplete": "The run is incomplete.",
    "expectation_failed": "A regression expectation failed.",
    "internal_error": "An internal operation failed.",
}


class ServiceError(Record):
    code: ErrorCode
    resource_id: ResourceId | None = None
    row: int | None = None
    reason: ResourceId | None = None

    @property
    def message(self) -> str:
        return _MESSAGES[self.code]

    def safe_dict(self) -> dict[str, object]:
        return {**self.model_dump(mode="json"), "message": self.message}


T = TypeVar("T")


class Success(Record, Generic[T]):
    data: T
    warnings: tuple[ServiceError, ...] = ()


class Failure(Record):
    error: ServiceError
    selection: SelectionDetails | None = None
