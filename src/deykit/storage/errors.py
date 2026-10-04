"""Storage failures expose stable reasons, never raw filesystem exceptions."""

from typing import NoReturn

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ErrorCode, ServiceError


def fail(reason: str, code: ErrorCode = "validation_error") -> NoReturn:
    raise ServiceFailure(ServiceError(code=code, reason=reason)) from None
