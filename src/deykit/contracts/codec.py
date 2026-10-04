"""Record codec validates the JSON envelope before Pydantic parses strict field types."""

from typing import TypeVar

from pydantic import ValidationError

from deykit.contracts.base import Record
from deykit.contracts.json_value import JsonError, parse_json

R = TypeVar("R", bound=Record)


def load_record(record_type: type[R], source: str | bytes) -> R:
    # stdlib/Pydantic alone accept duplicate keys; exact preflight is mandatory.
    value = parse_json(source)
    if not isinstance(value, dict):
        raise JsonError("record_object_required")
    if "schema_version" not in value:
        raise JsonError("missing_schema_version")
    try:
        return record_type.model_validate_json(source)
    except ValidationError:
        # Never leak exception input values or provider bodies to transport errors.
        raise JsonError("invalid_record") from None


def dump_record(record: Record) -> bytes:
    # Arbitrary user JSON is always a source STRING inside own records.
    source = record.model_dump_json().encode("utf-8")
    parse_json(source)
    return source
