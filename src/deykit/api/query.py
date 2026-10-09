"""Exact admission helpers for the string-valued HTTP query boundary."""

import re

from .errors import TransportFailure


def decimal(
    value: str,
    *,
    reason: str,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not str or re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is None:
        raise TransportFailure(422, "validation_error", reason)
    selected = int(value)
    if not minimum <= selected <= maximum:
        raise TransportFailure(422, "validation_error", reason)
    return selected


def boolean(value: str, *, reason: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise TransportFailure(422, "validation_error", reason)
