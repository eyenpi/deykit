"""Draft 2020-12 validation with exact numbers and local-only references."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from fractions import Fraction
from typing import Any

from jsonschema import Draft202012Validator, ValidationError, validators
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import NoSuchResource

from deykit.contracts.json_value import JsonError, JsonValue, parse_json


def _is_number(_: Any, value: Any) -> bool:
    return (type(value) is int or isinstance(value, Decimal)) and not isinstance(value, bool)


def _is_integer(checker: Any, value: Any) -> bool:
    return _is_number(checker, value) and value == int(value)


def _multiple_of(validator: Any, divisor: Any, instance: Any, schema: Any) -> Iterator[Any]:
    if validator.is_type(instance, "number"):
        if (Fraction(instance) / Fraction(divisor)).denominator != 1:
            yield ValidationError("not an exact multiple")


ExactValidator = validators.extend(  # type: ignore[no-untyped-call]
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine_many(
        {"number": _is_number, "integer": _is_integer}
    ),
    validators={"multipleOf": _multiple_of},
)


def _no_retrieval(uri: str) -> Any:
    raise NoSuchResource(uri)


def _schema_numbers(value: JsonValue) -> Any:
    # Meta-schema structural integer keywords (minItems, etc.) use Python integers.
    if isinstance(value, Decimal) and value == int(value):
        return int(value)
    if isinstance(value, list):
        return [_schema_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: _schema_numbers(item) for key, item in value.items()}
    return value


def compile_schema(source: str) -> Any:
    schema = _schema_numbers(parse_json(source))
    if not isinstance(schema, (dict, bool)):
        raise JsonError("invalid_schema")
    pending = [schema]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key in ("$ref", "$dynamicRef"):
                if key in node and (
                    not isinstance(node[key], str) or not node[key].startswith("#")
                ):
                    raise JsonError("remote_schema_reference")
            if (
                "$schema" in node
                and node["$schema"] != "https://json-schema.org/draft/2020-12/schema"
            ):
                raise JsonError("unsupported_schema_dialect")
            # Embedded identifiers change reference scope; version 1 supports local fragments only.
            if "$id" in node:
                raise JsonError("unsupported_schema_id")
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    try:
        ExactValidator.check_schema(schema)
    except SchemaError:
        raise JsonError("invalid_schema") from None
    return ExactValidator(
        schema,
        registry=Registry(retrieve=_no_retrieval),  # type: ignore[call-arg]
    )


def validate_json(schema_source: str, input_source: str) -> tuple[str, ...]:
    """Return deterministic safe keyword/path issues, without echoing input values."""
    validator = compile_schema(schema_source)
    value = parse_json(input_source)
    try:
        issues = tuple(
            sorted(
                f"{error.json_path}: {error.validator}" for error in validator.iter_errors(value)
            )
        )
    except RecursionError:
        raise JsonError("schema_resource_limit") from None
    except Exception as error:
        # The referencing library wraps missing local references in its own exception.
        if type(error).__name__ in {"_WrappedReferencingError", "Unresolvable", "PointerToNowhere"}:
            raise JsonError("unresolved_schema_reference") from None
        raise
    return issues
