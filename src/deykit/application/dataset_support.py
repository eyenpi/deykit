"""Typed boundaries shared only by dataset and import services."""

from dataclasses import dataclass
from typing import NoReturn, TypeVar

from pydantic import BaseModel, ValidationError

from deykit.application.errors import ServiceFailure
from deykit.contracts.base import Record
from deykit.contracts.codec import load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import JsonError, JsonValue, semantic_hash
from deykit.contracts.ports import ProjectSource, ResourceKey, StoredRecord
from deykit.contracts.records import CaseRecord, DatasetRecord

R = TypeVar("R", bound=Record)


def fail(reason: str, code: ErrorCode = "validation_error", *, row: int | None = None) -> NoReturn:
    raise ServiceFailure(ServiceError(code=code, reason=reason, row=row)) from None


def identifier(value: str) -> str:
    try:
        return validate_resource_id(value)
    except ValueError:
        raise ServiceFailure(
            ServiceError(code="validation_error", reason="invalid_resource_id")
        ) from None


def decoded(kind: type[R], record: StoredRecord) -> R:
    try:
        return load_record(kind, record.body)
    except (JsonError, ValidationError):
        raise ServiceFailure(
            ServiceError(code="validation_error", reason="invalid_record")
        ) from None


def required(source: ProjectSource, key: ResourceKey) -> StoredRecord:
    result = source.read(key)
    if result is None:
        raise ServiceFailure(ServiceError(code="not_found", resource_id=key.resource_id))
    return result


def intent(command: str, values: JsonValue) -> str:
    return safe_hash({"command": command, "values": values})


@dataclass(frozen=True)
class DatasetView:
    record: DatasetRecord
    etag: str


@dataclass(frozen=True)
class CaseView:
    record: CaseRecord
    etag: str
    duplicate_ids: tuple[str, ...] = ()


def cases(source: ProjectSource, dataset_id: str) -> tuple[StoredRecord, ...]:
    return tuple(
        required(source, ResourceKey("cases", key, (dataset_id,)))
        for key in source.list_ids("cases", (dataset_id,))
    )


def fingerprint(records: tuple[StoredRecord, ...]) -> str:
    return safe_hash(
        [
            [item.key.collection, list(item.key.scope), item.key.resource_id, item.etag]
            for item in sorted(
                records, key=lambda r: (r.key.collection, r.key.scope, r.key.resource_id)
            )
        ]
    )


def page(
    ids: tuple[str, ...], cursor: str | None, limit: int
) -> tuple[tuple[str, ...], str | None]:
    if type(limit) is not int or not 1 <= limit <= 500:
        fail("invalid_page_limit")
    if cursor is not None:
        identifier(cursor)
    remaining = tuple(key for key in sorted(ids) if cursor is None or key > cursor)
    return remaining[:limit], remaining[limit - 1] if len(remaining) > limit else None


def safe_hash(value: JsonValue) -> str:
    try:
        return semantic_hash(value)
    except JsonError as error:
        fail(error.code)


M = TypeVar("M", bound=BaseModel)


def validated_model(kind: type[M], value: object, reason: str) -> M:
    """Rebuild an untrusted model without invoking its serializers or trusting instances.

    Pydantic's model_copy/model_construct deliberately bypass validation. Projecting
    raw attributes recursively also prevents nested instances bypassing validation.
    Only bounded plain values are admitted; exceptions never include their contents.
    """
    if type(value) is not kind:
        fail(reason)
    count = 0

    def plain(item: object, depth: int = 0) -> object:
        nonlocal count
        count += 1
        if depth > 64 or count > 100_000:
            fail(reason)
        if isinstance(item, BaseModel):
            return plain(vars(item), depth + 1)
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                fail(reason)
            return {plain(key, depth + 1): plain(child, depth + 1) for key, child in item.items()}
        if type(item) is tuple:
            return tuple(plain(child, depth + 1) for child in item)
        if type(item) is list:
            return [plain(child, depth + 1) for child in item]
        if type(item) is str:
            try:
                item.encode("utf-8", "strict")
            except UnicodeError:
                fail(reason)
            return item
        if item is None or type(item) in (bool, int):
            return item
        fail(reason)

    try:
        return kind.model_validate(plain(value))
    except ValidationError:
        fail(reason)
