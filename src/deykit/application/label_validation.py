"""Strict raw request admission for label/split dataclasses, before hashing or source access."""

import re
from dataclasses import fields, is_dataclass
from typing import cast

from deykit.application.dataset_support import fail, identifier


def dto(value: object, expected: type[object], reason: str) -> dict[str, object]:
    if type(value) is not expected or not is_dataclass(value):
        fail(reason)
    try:
        return {field.name: object.__getattribute__(value, field.name) for field in fields(value)}
    except AttributeError:
        fail(reason)


def text(value: object, reason: str) -> str:
    if type(value) is not str:
        fail(reason)
    result = value
    try:
        result.encode("utf-8")
    except UnicodeError:
        fail(reason)
    return result


def resource(value: object) -> str:
    return identifier(text(value, "invalid_resource_id"))


def content_hash(value: object) -> str:
    result = text(value, "invalid_content_hash")
    if re.fullmatch("[0-9a-f]{64}", result) is None:
        fail("invalid_content_hash")
    return result


def integer(value: object, reason: str) -> int:
    if type(value) is not int:
        fail(reason)
    return value


def sequence(value: object, reason: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        fail(reason)
    return cast(tuple[object, ...], value)


def choice(value: object, choices: tuple[str, ...], reason: str) -> str:
    result = text(value, reason)
    if result not in choices:
        fail(reason)
    return result
