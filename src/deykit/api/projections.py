"""Typed service-to-transport projections shared across route families."""

from __future__ import annotations

from decimal import Decimal

from deykit.api.dto.common import ErrorDTO
from deykit.contracts.errors import ServiceError


def exact_display_tree(value: object) -> object:
    """Convert numeric leaves to text without passing through binary floats."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if type(value) is int or isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [exact_display_tree(item) for item in value]
    if isinstance(value, dict):
        return {str(key): exact_display_tree(item) for key, item in value.items()}
    raise TypeError("unsupported_projection_value")


def service_error(value: ServiceError | None) -> ErrorDTO | None:
    if value is None:
        return None
    return ErrorDTO(
        code=value.code,
        message=value.message,
        resource_id=value.resource_id,
        row=value.row if value.row is None or 0 <= value.row <= 9007199254740991 else None,
        reason=value.reason,
    )
