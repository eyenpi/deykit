"""Fixed safe transport messages; never reflect validation inputs or exception text."""

from uuid import uuid4

from starlette.responses import JSONResponse

from deykit.application.errors import ServiceFailure
from deykit.contracts.json_value import JsonError
from deykit.contracts.selection import SelectionDetails

from .dto.common import ErrorDTO, Failure

_MESSAGES = {
    "http_invalid": "The HTTP request is invalid.",
    "local_access_denied": "Local workspace access was denied.",
    "payload_too_large": "The request exceeds the permitted size.",
    "unsupported_media_type": "The request must contain UTF-8 JSON.",
    "method_not_allowed": "The HTTP method is not supported.",
    "service_unavailable": "The local service is unavailable.",
    "validation_error": "The supplied data is invalid.",
    "not_found": "The requested resource was not found.",
    "internal_error": "An internal operation failed.",
}
_STATUSES = {
    "validation_error": 422,
    "incompatible_data": 422,
    "preflight_failed": 422,
    "not_found": 404,
    "missing_fixture": 422,
    "conflict": 409,
    "execution_locked": 409,
    "run_incomplete": 409,
    "provider_auth": 502,
    "provider_rejected": 502,
    "response_invalid": 502,
    "expectation_failed": 422,
}


class TransportFailure(Exception):
    def __init__(self, status: int, code: str, reason: str) -> None:
        self.status, self.code, self.reason = status, code, reason
        super().__init__(code)


def safe_error(error: Exception) -> tuple[int, ErrorDTO, SelectionDetails | None]:
    if isinstance(error, TransportFailure):
        return (
            error.status,
            ErrorDTO(code=error.code, message=_MESSAGES[error.code], reason=error.reason),
            None,
        )
    if isinstance(error, ServiceFailure):
        record = error.error
        return (
            _STATUSES.get(record.code, 500),
            ErrorDTO(
                code=record.code,
                message=record.message,
                resource_id=record.resource_id,
                row=record.row
                if record.row is not None and 0 <= record.row <= 9007199254740991
                else None,
                reason=record.reason,
            ),
            error.selection,
        )
    if isinstance(error, JsonError):
        return (
            422,
            ErrorDTO(
                code="validation_error", message=_MESSAGES["validation_error"], reason=error.code
            ),
            None,
        )
    return (
        500,
        ErrorDTO(
            code="internal_error", message=_MESSAGES["internal_error"], correlation_id=uuid4().hex
        ),
        None,
    )


def error_response(error: Exception) -> JSONResponse:
    status, dto, selection = safe_error(error)
    return JSONResponse(
        Failure(error=dto, selection=selection).model_dump(mode="json"),
        status_code=status,
        headers={"Allow": "GET, HEAD, POST, PUT, PATCH, DELETE"} if status == 405 else None,
    )
