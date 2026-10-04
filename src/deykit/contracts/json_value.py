"""Exact JSON values and deykit-json-v1. No arithmetic uses Decimal context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Annotated, TypeAlias, cast

from pydantic import AfterValidator, StringConstraints

JsonValue: TypeAlias = "None | bool | str | int | Decimal | list[JsonValue] | dict[str, JsonValue]"
HASH_FORMAT = "deykit-json-v1"


class JsonError(ValueError):
    """A stable, safe reason with no source content attached."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class JsonLimits:
    max_bytes: int = 1_048_576
    max_depth: int = 64
    max_nodes: int = 100_000
    max_number_digits: int = 4096
    max_exponent: int = 10_000


DEFAULT_LIMITS = JsonLimits()


def _valid_string(value: str) -> None:
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise JsonError("invalid_unicode")


def parse_json(source: str | bytes, limits: JsonLimits = DEFAULT_LIMITS) -> JsonValue:
    """Parse exact numbers; reject duplicates, invalid Unicode and bounded resources."""
    if isinstance(source, bytes):
        if len(source) > limits.max_bytes:
            raise JsonError("json_resource_limit")
        try:
            source = source.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise JsonError("invalid_utf8") from None
    _valid_string(source)
    if len(source.encode("utf-8")) > limits.max_bytes:
        raise JsonError("json_resource_limit")

    def number(token: str) -> Decimal:
        coefficient, _, exponent = token.lower().partition("e")
        if sum(c.isdigit() for c in coefficient) > limits.max_number_digits:
            raise JsonError("json_resource_limit")
        # Bound before int conversion, including exponents with excessive leading zeros.
        if exponent and (len(exponent) > 7 or abs(int(exponent)) > limits.max_exponent):
            raise JsonError("json_resource_limit")
        try:
            result = Decimal(token)
            if not result.is_zero() and abs(result.adjusted()) > limits.max_exponent:
                raise JsonError("json_resource_limit")
            return result
        except InvalidOperation:
            raise JsonError("invalid_number") from None

    def constant(_: str) -> None:
        raise JsonError("nonfinite_number")

    def pairs(items: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in items:
            if key in result:
                raise JsonError("duplicate_key")
            result[key] = value
        return result

    # Reject excessive nesting before the stdlib recursive parser allocates containers.
    depth = 0
    quoted = escaped = False
    for char in source:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > limits.max_depth:
                raise JsonError("json_resource_limit")
        elif char in "]}":
            depth -= 1
    try:
        value = cast(
            JsonValue,
            json.loads(
                source,
                parse_int=number,
                parse_float=number,
                parse_constant=constant,
                object_pairs_hook=pairs,
            ),
        )
    except (json.JSONDecodeError, RecursionError):
        raise JsonError("invalid_json") from None
    pending = [value]
    nodes = 0
    while pending:
        node = pending.pop()
        nodes += 1
        if nodes > limits.max_nodes:
            raise JsonError("json_resource_limit")
        if isinstance(node, str):
            _valid_string(node)
        elif isinstance(node, dict):
            for key in node:
                _valid_string(key)
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return value


def _number(value: Decimal | int) -> str:
    decimal = Decimal(value) if isinstance(value, int) else value
    if not decimal.is_finite():
        raise JsonError("nonfinite_number")
    sign, digits_tuple, exponent = decimal.as_tuple()
    digits = "".join(str(digit) for digit in digits_tuple)
    if not any(digits_tuple):
        return "0"
    exponent = cast(int, exponent)
    scientific_exponent = exponent + len(digits) - 1
    digits = digits.rstrip("0")
    mantissa = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
    return ("-" if sign else "") + mantissa + "e" + str(scientific_exponent)


def dump_json(value: JsonValue, *, sort_keys: bool = False) -> str:
    """Exact UTF-8 JSON text. Object insertion order is retained for provider bodies."""

    def encode(node: JsonValue) -> str:
        if node is None:
            return "null"
        if type(node) is bool:
            return "true" if node else "false"
        if isinstance(node, str):
            _valid_string(node)
            return json.dumps(node, ensure_ascii=False)
        if type(node) is int or isinstance(node, Decimal):
            return _number(node)
        if isinstance(node, list):
            return "[" + ",".join(encode(item) for item in node) + "]"
        if isinstance(node, dict):
            if any(not isinstance(key, str) for key in node):
                raise JsonError("invalid_json_type")
            keys = sorted(node) if sort_keys else node.keys()
            return "{" + ",".join(encode(key) + ":" + encode(node[key]) for key in keys) + "}"
        raise JsonError("invalid_json_type")

    try:
        source = encode(value)
    except RecursionError:
        raise JsonError("json_resource_limit") from None
    parse_json(source)  # Apply identical limits to constructed values.
    return source


def canonical_bytes(value: JsonValue) -> bytes:
    return dump_json(value, sort_keys=True).encode("utf-8")


def semantic_hash(value: JsonValue) -> str:
    return hashlib.sha256(HASH_FORMAT.encode() + b"\n" + canonical_bytes(value)).hexdigest()


def bytes_hash(body: bytes) -> str:
    """Wire identity has no semantic profile prefix and never reorders the body."""
    return hashlib.sha256(body).hexdigest()


def validate_source(source: str) -> str:
    parse_json(source)
    return source


JsonSource = Annotated[str, StringConstraints(strict=True), AfterValidator(validate_source)]


@dataclass(frozen=True)
class JsonDocument:
    """Immutable source; each value access is a fresh tree, so callers cannot mutate evidence."""

    source: str

    def __post_init__(self) -> None:
        parse_json(self.source)

    @property
    def value(self) -> JsonValue:
        return parse_json(self.source)

    @property
    def content_hash(self) -> str:
        return semantic_hash(self.value)

    def select(self, fields: tuple[str, ...]) -> JsonDocument:
        value = self.value
        if not isinstance(value, dict):
            raise JsonError("object_required")
        if len(fields) != len(set(fields)):
            raise JsonError("duplicate_selection")
        if any(field not in value for field in fields):
            raise JsonError("missing_selected_field")
        return JsonDocument(dump_json({field: value[field] for field in fields}))
