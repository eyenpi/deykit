"""Portable IDs are path segments, never names or paths."""

import re
from typing import Annotated
from uuid import uuid4

from pydantic import AfterValidator, StringConstraints

_RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"} | {
    f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
}


def validate_resource_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_resource_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("invalid_resource_id")
    if value.upper() in _RESERVED:
        raise ValueError("reserved_resource_id")
    return value


ResourceId = Annotated[str, StringConstraints(strict=True), AfterValidator(validate_resource_id)]
ContentHash = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def new_id() -> str:
    return uuid4().hex
