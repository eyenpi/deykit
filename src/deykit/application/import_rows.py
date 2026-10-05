"""Bounded source parsing and row mapping with exact JSON values."""

import csv
import io
from dataclasses import dataclass
from typing import Literal, cast

from deykit.application.dataset_support import fail
from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonError, JsonValue, dump_json, parse_json
from deykit.domain.import_mapping import ImportMapping

MAX_IMPORT_BYTES = 8_388_608
MAX_IMPORT_ROWS = 10_000


@dataclass(frozen=True)
class SourceRow:
    row: int
    line: int
    value: dict[str, JsonValue] | None
    error: ServiceError | None = None


def source_text(source: str | bytes) -> str:
    if type(source) not in (str, bytes):
        fail("invalid_import_source")
    try:
        text = source.decode("utf-8", "strict") if isinstance(source, bytes) else source
        if len(text.encode("utf-8", "strict")) > MAX_IMPORT_BYTES:
            fail("import_resource_limit")
    except UnicodeError:
        fail("invalid_utf8")
    if text.startswith("\ufeff"):
        fail("unexpected_byte_order_mark")
    return text


def rows(text: str, format: Literal["csv", "jsonl"]) -> tuple[SourceRow, ...]:
    result: list[SourceRow] = []
    if format == "jsonl":
        # Only LF/CRLF delimit rows; Unicode line separators inside JSON strings are data.
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        for index, line in enumerate(lines, 1):
            if index > MAX_IMPORT_ROWS:
                fail("import_resource_limit")
            try:
                value = parse_json(line)
                if not isinstance(value, dict):
                    raise JsonError("row_object_required")
                result.append(SourceRow(index, index, value))
            except JsonError as error:
                result.append(
                    SourceRow(
                        index,
                        index,
                        None,
                        ServiceError(code="validation_error", row=index, reason=error.code),
                    )
                )
    elif format == "csv":
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        try:
            headers = next(reader, None)
            if (
                not headers
                or any(not header for header in headers)
                or len(set(headers)) != len(headers)
            ):
                fail("invalid_csv_header")
            for index, cells in enumerate(reader, 1):
                if index > MAX_IMPORT_ROWS:
                    fail("import_resource_limit")
                if len(cells) != len(headers):
                    result.append(
                        SourceRow(
                            index,
                            reader.line_num,
                            None,
                            ServiceError(
                                code="validation_error", row=index, reason="csv_column_count"
                            ),
                        )
                    )
                else:
                    result.append(
                        SourceRow(index, reader.line_num, dict(zip(headers, cells, strict=True)))
                    )
        except csv.Error as error:
            if "field larger than field limit" in str(error):
                fail("csv_field_resource_limit")
            # After a lexical CSV error, row boundaries are not trustworthy.
            fail("malformed_csv")
    else:
        fail("invalid_import_format")
    if not result:
        fail("empty_import")
    return tuple(result)


def _get(row: dict[str, JsonValue], column: str, *, decode: bool = False) -> JsonValue:
    if column not in row:
        fail("missing_column")
    value = row[column]
    if decode:
        if not isinstance(value, str):
            fail("json_cell_requires_string")
        try:
            return parse_json(value)
        except JsonError as error:
            fail(error.code)
    return value


def mapped(
    row: dict[str, JsonValue], mapping: ImportMapping
) -> tuple[str | None, CaseInput, tuple[str, ...]]:
    if mapping.input_column is not None:
        state = _get(row, mapping.input_column, decode=mapping.input_parse_json)
    else:
        state = {
            field.target: _get(row, field.source, decode=field.parse_json)
            for field in mapping.fields
        }
    kind = str if mapping.input_kind == "text" else dict
    if not isinstance(state, kind):
        fail("input_shape_mismatch")
    case_id = _get(row, mapping.id_column) if mapping.id_column else None
    if case_id is not None and not isinstance(case_id, str):
        fail("invalid_case_id")
    if case_id == "":
        case_id = None
    expectations: tuple[str, ...] = ()
    if mapping.expected_column:
        value = _get(row, mapping.expected_column)
        if value not in (None, ""):
            if mapping.expected_parse_json:
                value = _get(row, mapping.expected_column, decode=True)
            if isinstance(value, str):
                expectations = (value,)
            elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
                expectations = tuple(cast(list[str], value))
            else:
                fail("invalid_expected_set")
            aliases = {item.value: item.option_id for item in mapping.option_aliases}
            expectations = tuple(aliases.get(item, item) for item in expectations)
            if len(set(expectations)) != len(expectations):
                fail("duplicate_expected_option")
    group = _get(row, mapping.group_column) if mapping.group_column else None
    if group == "":
        group = None
    if group is not None and not isinstance(group, str):
        fail("invalid_group")
    tags: tuple[str, ...] = ()
    if mapping.tags_column:
        tag_values = _get(row, mapping.tags_column, decode=mapping.tags_parse_json)
        if isinstance(tag_values, str):
            tags = (tag_values,) if tag_values else ()
        elif isinstance(tag_values, list) and all(isinstance(item, str) for item in tag_values):
            tags = tuple(cast(list[str], tag_values))
        else:
            fail("invalid_tags")
    split = _get(row, mapping.split_column) if mapping.split_column else "development"
    if not isinstance(split, str) or split not in {"development", "calibration", "test"}:
        fail("invalid_split")
    metadata = (
        _get(row, mapping.metadata_column, decode=mapping.metadata_parse_json)
        if (mapping.metadata_column)
        else {}
    )
    try:
        case_input = CaseInput(
            input_kind=mapping.input_kind,
            input_source=dump_json(state),
            tags=tags,
            split=cast(Literal["development", "calibration", "test"], split),
            group_id=group,
            metadata_source=dump_json(metadata),
        )
    except ValueError:
        raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_case")) from None
    return case_id, case_input, expectations
