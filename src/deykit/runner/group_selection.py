"""One exact codec and intent function for persisted execution-group selection."""

import re
from dataclasses import dataclass
from typing import cast

from deykit.application.dataset_support import fail
from deykit.contracts.errors import ErrorCode
from deykit.contracts.json_value import (
    JsonDocument,
    JsonError,
    JsonValue,
    dump_json,
    semantic_hash,
)
from deykit.runner.group_models import GroupKind

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REVIEW_VERSION = "group-start-review-v1"


@dataclass(frozen=True)
class GroupStartSelection:
    stored_source: str
    original_selection: JsonValue
    expected_review_context_hash: str | None


def _invalid(
    reason: str = "invalid_group_selection", code: ErrorCode = "incompatible_data"
) -> None:
    fail(reason, code)


def _selection(
    value: JsonValue,
    expected_kind: GroupKind | None,
    *,
    code: ErrorCode = "incompatible_data",
) -> dict[str, JsonValue]:
    if type(value) is not dict or set(value) != {"kind", "request"}:
        _invalid(code=code)
    kind, request = value["kind"], value["request"]
    if kind not in ("choice_order", "regression_check") or type(request) is not dict:
        _invalid(code=code)
    if expected_kind is not None and kind != expected_kind:
        _invalid(code=code)
    return cast(dict[str, JsonValue], value)


def encode_group_start_selection(
    original_source: str, *, expected_review_context_hash: str | None = None
) -> GroupStartSelection:
    if type(original_source) is not str:
        _invalid(code="validation_error")
    try:
        value = JsonDocument(original_source).value
    except JsonError:
        _invalid(code="validation_error")
    original = _selection(value, None, code="validation_error")
    if expected_review_context_hash is None:
        return GroupStartSelection(original_source, original, None)
    if (
        type(expected_review_context_hash) is not str
        or _HASH.fullmatch(expected_review_context_hash) is None
    ):
        fail("invalid_review_context_hash")
    stored = dump_json(
        {
            "kind": original["kind"],
            "request": original["request"],
            "review": {
                "version": _REVIEW_VERSION,
                "expected_review_context_hash": expected_review_context_hash,
            },
        }
    )
    return GroupStartSelection(stored, original, expected_review_context_hash)


def decode_group_start_selection(
    stored_source: str, *, expected_kind: GroupKind | None = None
) -> GroupStartSelection:
    if type(stored_source) is not str:
        _invalid()
    try:
        value = JsonDocument(stored_source).value
    except JsonError:
        _invalid()
    if type(value) is not dict:
        _invalid()
    if set(value) == {"kind", "request"}:
        original = _selection(value, expected_kind)
        return GroupStartSelection(stored_source, original, None)
    if set(value) != {"kind", "request", "review"}:
        _invalid()
    kind, request, review = value["kind"], value["request"], value["review"]
    original_value: JsonValue = {"kind": kind, "request": request}
    original = _selection(original_value, expected_kind)
    if type(review) is not dict or set(review) != {
        "version",
        "expected_review_context_hash",
    }:
        _invalid()
    expected = review["expected_review_context_hash"]
    if (
        review["version"] != _REVIEW_VERSION
        or type(expected) is not str
        or not _HASH.fullmatch(expected)
    ):
        _invalid()
    return GroupStartSelection(stored_source, original, expected)


def group_start_intent(selection: GroupStartSelection) -> str:
    if selection.expected_review_context_hash is None:
        payload: JsonValue = {
            "command": "execution_group.start",
            "selection": selection.original_selection,
        }
    else:
        payload = {
            "command": "execution_group.start.reviewed-v1",
            "selection": selection.original_selection,
            "expected_review_context_hash": selection.expected_review_context_hash,
        }
    return semantic_hash(payload)
