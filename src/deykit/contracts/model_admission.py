"""Bounded strict reconstruction of untrusted Pydantic models."""

from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class ModelInvalid(ValueError):
    """Only a caller-chosen safe reason; never carries user fields or values."""


def admit_model(kind: type[M], value: object, reason: str, *, max_nodes: int = 100_000) -> M:
    """Rebuild all nested fields, including instances made with model_copy/construct."""
    if type(value) is not kind:
        raise ModelInvalid(reason)
    count = 0

    def plain(item: object, depth: int = 0) -> object:
        nonlocal count
        count += 1
        if depth > 64 or count > max_nodes:
            raise ModelInvalid(reason)
        if isinstance(item, BaseModel):
            return plain(vars(item), depth + 1)
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ModelInvalid(reason)
            return {plain(key, depth + 1): plain(child, depth + 1) for key, child in item.items()}
        if type(item) is tuple:
            return tuple(plain(child, depth + 1) for child in item)
        if type(item) is list:
            return [plain(child, depth + 1) for child in item]
        if type(item) is str:
            try:
                item.encode("utf-8", "strict")
            except UnicodeError:
                raise ModelInvalid(reason) from None
            return item
        if item is None or type(item) in (bool, int):
            return item
        raise ModelInvalid(reason)

    try:
        return kind.model_validate(plain(value))
    except ValidationError:
        raise ModelInvalid(reason) from None
