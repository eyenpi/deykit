"""Pure exact-source projections and edits for browser-facing authoring forms."""

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Literal, Self, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue, bytes_hash, dump_json
from deykit.contracts.records import ChoiceDefinition
from deykit.contracts.schema import compile_schema
from deykit.domain.import_mapping import ImportMapping


@dataclass(frozen=True)
class ValidationAdviceV1:
    kind: Literal["validation", "advice"]
    code: str
    path: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditorOptionV1:
    id: str
    name: str
    description: str | None


@dataclass(frozen=True)
class EditorFormV1:
    input_kind: Literal["text", "json"]
    selected_fields: tuple[str, ...]
    input_schema_source: str | None
    question_id: str
    instructions: str
    options: tuple[EditorOptionV1, ...]


@dataclass(frozen=True)
class EditorProjectionV1:
    schema_version: Literal[1]
    editor_source: str
    source_hash: str | None
    form: EditorFormV1 | None
    form_unavailable_reason: str | None
    validation_advice: tuple[ValidationAdviceV1, ...]


@dataclass(frozen=True)
class EditorTransformV1:
    schema_version: Literal[1]
    original_source_hash: str
    editor_source: str
    source_hash: str
    projection: EditorProjectionV1
    validation_advice: tuple[ValidationAdviceV1, ...]


@dataclass(frozen=True)
class SchemaFieldV1:
    name: str
    field_type: str | None
    required: bool
    editable: bool
    advanced_keywords: tuple[str, ...]


@dataclass(frozen=True)
class SchemaProjectionV1:
    schema_version: Literal[1]
    schema_source: str | None
    source_hash: str | None
    fields: tuple[SchemaFieldV1, ...] | None
    advanced_keywords: tuple[str, ...]
    form_unavailable_reason: str | None
    validation_advice: tuple[ValidationAdviceV1, ...]


@dataclass(frozen=True)
class CaseInputProjectionV1:
    schema_version: Literal[1]
    input_kind: Literal["text", "json"]
    input_source: str
    source_hash: str | None
    text_value: str | None
    form_unavailable_reason: str | None


@dataclass(frozen=True)
class EncodedInputV1:
    schema_version: Literal[1]
    input_source: str
    source_hash: str


@dataclass(frozen=True)
class MappingFieldFormV1:
    source: str
    target: str
    parse_json: bool


@dataclass(frozen=True)
class MappingAliasFormV1:
    value: str
    option_id: str


@dataclass(frozen=True)
class MappingFormV1:
    schema_version: Literal[1]
    input_kind: Literal["text", "json"]
    input_column: str | None
    input_parse_json: bool
    fields: tuple[MappingFieldFormV1, ...]
    id_column: str | None
    expected_column: str | None
    expected_parse_json: bool
    option_aliases: tuple[MappingAliasFormV1, ...]
    group_column: str | None
    tags_column: str | None
    tags_parse_json: bool
    split_column: str | None
    metadata_column: str | None
    metadata_parse_json: bool


@dataclass(frozen=True)
class MappingProjectionV1:
    schema_version: Literal[1]
    mapping_source: str
    source_hash: str | None
    form: MappingFormV1 | None
    form_unavailable_reason: str | None
    validation_advice: tuple[ValidationAdviceV1, ...]


@dataclass(frozen=True)
class MappingTransformV1:
    schema_version: Literal[1]
    original_source_hash: str
    mapping_source: str
    source_hash: str
    projection: MappingProjectionV1
    validation_advice: tuple[ValidationAdviceV1, ...]


class _Edit(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class SetInstructions(_Edit):
    kind: Literal["set_instructions"]
    value: str


class AddOption(_Edit):
    kind: Literal["add_option"]
    id: str
    name: str
    description: str | None


class RemoveOption(_Edit):
    kind: Literal["remove_option"]
    id: str


class RenameOption(_Edit):
    kind: Literal["rename_option"]
    id: str
    name: str


class DescribeOption(_Edit):
    kind: Literal["describe_option"]
    id: str
    description: str | None


class ReorderOptions(_Edit):
    kind: Literal["reorder_options"]
    option_ids: tuple[str, ...]


class SetInputKind(_Edit):
    kind: Literal["set_input_kind"]
    input_kind: Literal["text", "json"]


class SetSelectedFields(_Edit):
    kind: Literal["set_selected_fields"]
    selected_fields: tuple[str, ...]


class ReplaceSchema(_Edit):
    kind: Literal["replace_schema"]
    input_schema_source: str | None


class SchemaField(_Edit):
    kind: Literal["schema_field"]
    name: str
    field_type: str
    required: bool


class RemoveSchemaField(_Edit):
    kind: Literal["remove_schema_field"]
    name: str


EditorEditV1: TypeAlias = Annotated[
    SetInstructions
    | AddOption
    | RemoveOption
    | RenameOption
    | DescribeOption
    | ReorderOptions
    | SetInputKind
    | SetSelectedFields
    | ReplaceSchema
    | SchemaField
    | RemoveSchemaField,
    Field(discriminator="kind"),
]
_EDITOR_EDIT = TypeAdapter(EditorEditV1)


class SetMappingField(_Edit):
    kind: Literal["set"]
    field: Literal[
        "input_kind",
        "input_column",
        "input_parse_json",
        "id_column",
        "expected_column",
        "expected_parse_json",
        "group_column",
        "tags_column",
        "tags_parse_json",
        "split_column",
        "metadata_column",
        "metadata_parse_json",
    ]
    value: str | bool | None

    @model_validator(mode="after")
    def exact_field_value(self) -> Self:
        if self.field == "input_kind":
            valid = type(self.value) is str and self.value in ("text", "json")
        elif self.field in {
            "input_parse_json",
            "expected_parse_json",
            "tags_parse_json",
            "metadata_parse_json",
        }:
            valid = type(self.value) is bool
        else:
            valid = self.value is None or type(self.value) is str
        if not valid:
            raise ValueError("mapping_edit_value_mismatch")
        return self


class ReplaceMappingField(_Edit):
    source: str
    target: str
    parse_json: bool


class ReplaceMappingAlias(_Edit):
    value: str
    option_id: str


class ReplaceMappingFields(_Edit):
    kind: Literal["replace_fields"]
    fields: tuple[ReplaceMappingField, ...]


class ReplaceOptionAliases(_Edit):
    kind: Literal["replace_option_aliases"]
    option_aliases: tuple[ReplaceMappingAlias, ...]


MappingEditV1: TypeAlias = Annotated[
    SetMappingField | ReplaceMappingFields | ReplaceOptionAliases,
    Field(discriminator="kind"),
]
_MAPPING_EDIT = TypeAdapter(MappingEditV1)

_EDITOR_KEYS = {
    "schema_version",
    "input_kind",
    "input_schema_source",
    "selected_fields",
    "questions",
}
_QUESTION_KEYS = {"id", "kind", "instructions", "options"}
_OPTION_KEYS = {"id", "name", "description"}
_MAPPING_KEYS = {
    "schema_version",
    "input_kind",
    "input_column",
    "input_parse_json",
    "fields",
    "id_column",
    "expected_column",
    "expected_parse_json",
    "option_aliases",
    "group_column",
    "tags_column",
    "tags_parse_json",
    "split_column",
    "metadata_column",
    "metadata_parse_json",
}
_MAPPING_STRING_FIELDS = {
    "input_column",
    "id_column",
    "expected_column",
    "group_column",
    "tags_column",
    "split_column",
    "metadata_column",
}
_MAPPING_FLAG_FIELDS = {
    "input_parse_json",
    "expected_parse_json",
    "tags_parse_json",
    "metadata_parse_json",
}
_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}
_SCHEMA_COMMON = {"$schema", "description", "properties", "required", "title", "type"}


def _version_one(value: JsonValue) -> bool:
    if type(value) is int:
        return value == 1
    return (
        type(value) is Decimal
        and value == 1
        and value.as_tuple().exponent >= 0
    )


def _source_hash(source: str) -> str | None:
    try:
        return bytes_hash(source.encode("utf-8", "strict"))
    except UnicodeError:
        return None


def _notices(error: ValidationError) -> tuple[ValidationAdviceV1, ...]:
    return tuple(
        ValidationAdviceV1(
            "validation",
            str(item.get("type", "invalid_value")),
            tuple(str(part) for part in item.get("loc", ())),
        )
        for item in error.errors(include_input=False, include_context=False)
    )


def _editor_value(editor_source: str) -> dict[str, JsonValue] | None:
    try:
        value = JsonDocument(editor_source).value
    except JsonError:
        return None
    if type(value) is not dict or set(value).difference(_EDITOR_KEYS):
        return None
    if "schema_version" in value and not _version_one(value["schema_version"]):
        return None
    kind = value.get("input_kind")
    selected = value.get("selected_fields", [])
    schema_source = value.get("input_schema_source")
    questions = value.get("questions")
    if (
        type(kind) is not str
        or kind not in ("text", "json")
        or type(selected) is not list
        or any(type(item) is not str for item in selected)
        or (schema_source is not None and type(schema_source) is not str)
        or type(questions) is not list
        or len(questions) != 1
    ):
        return None
    question = questions[0]
    if (
        type(question) is not dict
        or set(question).difference(_QUESTION_KEYS)
        or type(question.get("id")) is not str
        or type(question.get("instructions")) is not str
        or ("kind" in question and question["kind"] != "choice")
        or type(question.get("options")) is not list
    ):
        return None
    for option in question["options"]:
        if (
            type(option) is not dict
            or set(option).difference(_OPTION_KEYS)
            or type(option.get("id")) is not str
            or type(option.get("name")) is not str
            or (
                "description" in option
                and option["description"] is not None
                and type(option["description"]) is not str
            )
        ):
            return None
    return cast(dict[str, JsonValue], value)


def project_editor(editor_source: str) -> EditorProjectionV1:
    if type(editor_source) is not str:
        raise ValueError("invalid_editor_source")
    digest = _source_hash(editor_source)
    value = _editor_value(editor_source)
    if digest is None:
        reason = "invalid_unicode"
    elif value is None:
        try:
            JsonDocument(editor_source)
        except JsonError as error:
            reason = error.code
        else:
            reason = "unsupported_editor_shape"
    else:
        reason = None
    if value is None or reason is not None:
        return EditorProjectionV1(1, editor_source, digest, None, reason, ())
    question = cast(dict[str, JsonValue], value["questions"][0])
    form = EditorFormV1(
        cast(Literal["text", "json"], value["input_kind"]),
        tuple(cast(list[str], value.get("selected_fields", []))),
        cast(str | None, value.get("input_schema_source")),
        cast(str, question["id"]),
        cast(str, question["instructions"]),
        tuple(
            EditorOptionV1(
                cast(str, item["id"]),
                cast(str, item["name"]),
                cast(str | None, item.get("description")),
            )
            for item in cast(list[dict[str, JsonValue]], question["options"])
        ),
    )
    try:
        ChoiceDefinition.model_validate_json(editor_source)
    except ValidationError as error:
        validation_advice = _notices(error)
    else:
        validation_advice = ()
    return EditorProjectionV1(1, editor_source, digest, form, None, validation_advice)


def _require_editor(value: dict[str, JsonValue]) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    questions = cast(list[JsonValue], value["questions"])
    question = cast(dict[str, JsonValue], questions[0])
    options = cast(list[JsonValue], question["options"])
    return question, options


def _schema_parts(source: str) -> tuple[dict[str, JsonValue], dict[str, JsonValue], list[str]]:
    parsed = JsonDocument(source).value
    if type(parsed) is not dict:
        raise ValueError("schema_form_unavailable")
    properties = parsed.get("properties", {})
    required = parsed.get("required", [])
    if type(properties) is not dict or any(type(key) is not str for key in properties):
        raise ValueError("schema_properties_unavailable")
    if type(required) is not list or any(type(item) is not str for item in required):
        raise ValueError("schema_required_unavailable")
    return (
        cast(dict[str, JsonValue], parsed),
        cast(dict[str, JsonValue], properties),
        cast(list[str], required),
    )


def project_schema(schema_source: str | None) -> SchemaProjectionV1:
    if schema_source is None:
        return SchemaProjectionV1(1, None, None, None, (), None, ())
    if type(schema_source) is not str:
        raise ValueError("invalid_schema_source")
    digest = _source_hash(schema_source)
    if digest is None:
        return SchemaProjectionV1(1, schema_source, None, None, (), "invalid_unicode", ())
    try:
        compile_schema(schema_source)
        root, properties, required = _schema_parts(schema_source)
    except JsonError as error:
        return SchemaProjectionV1(
            schema_version=1,
            schema_source=schema_source,
            source_hash=digest,
            fields=None,
            advanced_keywords=(),
            form_unavailable_reason=error.code,
            validation_advice=(),
        )
    except ValueError as error:
        return SchemaProjectionV1(
            schema_version=1,
            schema_source=schema_source,
            source_hash=digest,
            fields=None,
            advanced_keywords=(),
            form_unavailable_reason=str(error) or "schema_form_unavailable",
            validation_advice=(),
        )
    fields: list[SchemaFieldV1] = []
    for name, raw in properties.items():
        if type(raw) is not dict:
            fields.append(SchemaFieldV1(name, None, name in required, False, ()))
            continue
        field_type = raw.get("type")
        simple_type = field_type if type(field_type) is str else None
        valid_type = simple_type is None or simple_type in _SCHEMA_TYPES
        advanced = tuple(sorted(set(raw).difference({"type"})))
        fields.append(
            SchemaFieldV1(
                name,
                simple_type,
                name in required,
                valid_type,
                advanced,
            )
        )
    advanced_keywords = tuple(sorted(set(root).difference(_SCHEMA_COMMON)))
    advice = (
        (ValidationAdviceV1("advice", "advanced_schema_keywords"),)
        if advanced_keywords or any(item.advanced_keywords for item in fields)
        else ()
    )
    return SchemaProjectionV1(
        1, schema_source, digest, tuple(fields), advanced_keywords, None, advice
    )


def _edit_schema_field(source: str | None, name: str, field_type: str, required: bool) -> str:
    if source is None or field_type not in _SCHEMA_TYPES:
        raise ValueError("schema_field_edit_unavailable")
    projection = project_schema(source)
    if projection.fields is None:
        raise ValueError("schema_field_edit_unavailable")
    existing = next((field for field in projection.fields if field.name == name), None)
    if existing is not None and not existing.editable:
        raise ValueError("schema_field_edit_unsafe")
    root, properties, required_fields = _schema_parts(source)
    raw_field = properties.get(name, {})
    if type(raw_field) is not dict:
        raise ValueError("schema_field_edit_unsafe")
    changed_field = dict(raw_field)
    changed_field["type"] = field_type
    properties[name] = changed_field
    root["properties"] = properties
    if required:
        if name not in required_fields:
            required_fields.append(name)
    else:
        required_fields = [item for item in required_fields if item != name]
    if required_fields or "required" in root:
        root["required"] = required_fields
    result = dump_json(root)
    compile_schema(result)
    return result


def _remove_schema_field(source: str | None, name: str) -> str:
    if source is None:
        raise ValueError("schema_field_edit_unavailable")
    projection = project_schema(source)
    if projection.fields is None:
        raise ValueError("schema_field_edit_unavailable")
    existing = next((field for field in projection.fields if field.name == name), None)
    if existing is None or not existing.editable:
        raise ValueError("schema_field_edit_unsafe")
    root, properties, required_fields = _schema_parts(source)
    del properties[name]
    root["properties"] = properties
    required_fields = [item for item in required_fields if item != name]
    if required_fields or "required" in root:
        root["required"] = required_fields
    result = dump_json(root)
    compile_schema(result)
    return result


def transform_editor(editor_source: str, edit: EditorEditV1) -> EditorTransformV1:
    projection = project_editor(editor_source)
    if projection.form is None or projection.source_hash is None:
        raise ValueError("editor_form_unavailable")
    try:
        admitted = _EDITOR_EDIT.validate_python(edit)
        value = JsonDocument(editor_source).value
        if type(value) is not dict:
            raise ValueError("editor_form_unavailable")
        transformed = cast(dict[str, JsonValue], deepcopy(value))
        question, options = _require_editor(transformed)
        if isinstance(admitted, SetInstructions):
            question["instructions"] = admitted.value
        elif isinstance(admitted, AddOption):
            if any(type(option) is dict and option.get("id") == admitted.id for option in options):
                raise ValueError("duplicate_option_id")
            options.append(
                {"id": admitted.id, "name": admitted.name, "description": admitted.description}
            )
        elif isinstance(admitted, RemoveOption):
            index = next(
                (
                    index
                    for index, option in enumerate(options)
                    if type(option) is dict and option.get("id") == admitted.id
                ),
                None,
            )
            if index is None:
                raise ValueError("option_not_found")
            del options[index]
        elif isinstance(admitted, RenameOption):
            option = _option_by_id(options, admitted.id)
            option["name"] = admitted.name
        elif isinstance(admitted, DescribeOption):
            option = _option_by_id(options, admitted.id)
            option["description"] = admitted.description
        elif isinstance(admitted, ReorderOptions):
            existing = {cast(str, option["id"]): option for option in options}
            if len(existing) != len(options) or set(existing) != set(admitted.option_ids):
                raise ValueError("invalid_option_order")
            options[:] = [existing[key] for key in admitted.option_ids]
        elif isinstance(admitted, SetInputKind):
            transformed["input_kind"] = admitted.input_kind
        elif isinstance(admitted, SetSelectedFields):
            transformed["selected_fields"] = list(admitted.selected_fields)
        elif isinstance(admitted, ReplaceSchema):
            transformed["input_schema_source"] = admitted.input_schema_source
        elif isinstance(admitted, SchemaField):
            schema_source = transformed.get("input_schema_source")
            transformed["input_schema_source"] = _edit_schema_field(
                cast(str | None, schema_source),
                admitted.name,
                admitted.field_type,
                admitted.required,
            )
        elif isinstance(admitted, RemoveSchemaField):
            schema_source = transformed.get("input_schema_source")
            transformed["input_schema_source"] = _remove_schema_field(
                cast(str | None, schema_source), admitted.name
            )
        else:
            raise ValueError("unsupported_editor_edit")
        output = dump_json(transformed)
    except (JsonError, ValidationError, ValueError, TypeError) as error:
        raise ValueError("invalid_editor_edit") from error
    result = project_editor(output)
    return EditorTransformV1(
        1,
        projection.source_hash,
        output,
        cast(str, result.source_hash),
        result,
        result.validation_advice,
    )


def _option_by_id(options: list[JsonValue], option_id: str) -> dict[str, JsonValue]:
    for option in options:
        if type(option) is dict and option.get("id") == option_id:
            return cast(dict[str, JsonValue], option)
    raise ValueError("option_not_found")


def project_case_input(
    input_kind: Literal["text", "json"], input_source: str
) -> CaseInputProjectionV1:
    if type(input_source) is not str or input_kind not in ("text", "json"):
        raise ValueError("invalid_case_input_source")
    digest = _source_hash(input_source)
    if input_kind == "json" or digest is None:
        return CaseInputProjectionV1(
            1,
            input_kind,
            input_source,
            digest,
            None,
            "invalid_unicode" if digest is None else None,
        )
    try:
        value = JsonDocument(input_source).value
    except JsonError as error:
        return CaseInputProjectionV1(1, input_kind, input_source, digest, None, error.code)
    if type(value) is not str:
        return CaseInputProjectionV1(
            1, input_kind, input_source, digest, None, "text_input_not_json_string"
        )
    return CaseInputProjectionV1(1, input_kind, input_source, digest, value, None)


def encode_text_input(text_value: str) -> EncodedInputV1:
    if type(text_value) is not str:
        raise ValueError("invalid_text_input")
    source = dump_json(text_value)
    digest = _source_hash(source)
    if digest is None:
        raise ValueError("invalid_text_input")
    return EncodedInputV1(1, source, digest)


def _mapping_form(value: dict[str, JsonValue]) -> MappingFormV1 | None:
    if set(value).difference(_MAPPING_KEYS):
        return None
    version = value.get("schema_version", 1)
    if not _version_one(version):
        return None
    input_kind = value.get("input_kind")
    if type(input_kind) is not str or input_kind not in ("text", "json"):
        return None
    for name in _MAPPING_STRING_FIELDS:
        if name in value and value[name] is not None and type(value[name]) is not str:
            return None
    for name in _MAPPING_FLAG_FIELDS:
        if name in value and type(value[name]) is not bool:
            return None
    raw_fields = value.get("fields", [])
    raw_aliases = value.get("option_aliases", [])
    if type(raw_fields) is not list or any(
        type(item) is not dict
        or set(item) != {"source", "target", "parse_json"}
        or type(item.get("source")) is not str
        or type(item.get("target")) is not str
        or type(item.get("parse_json")) is not bool
        for item in raw_fields
    ):
        return None
    if type(raw_aliases) is not list or any(
        type(item) is not dict
        or set(item) != {"value", "option_id"}
        or type(item.get("value")) is not str
        or type(item.get("option_id")) is not str
        for item in raw_aliases
    ):
        return None
    return MappingFormV1(
        1,
        cast(Literal["text", "json"], input_kind),
        cast(str | None, value.get("input_column")),
        cast(bool, value.get("input_parse_json", False)),
        tuple(
            MappingFieldFormV1(
                cast(str, item["source"]),
                cast(str, item["target"]),
                cast(bool, item["parse_json"]),
            )
            for item in raw_fields
        ),
        cast(str | None, value.get("id_column")),
        cast(str | None, value.get("expected_column")),
        cast(bool, value.get("expected_parse_json", False)),
        tuple(
            MappingAliasFormV1(cast(str, item["value"]), cast(str, item["option_id"]))
            for item in raw_aliases
        ),
        cast(str | None, value.get("group_column")),
        cast(str | None, value.get("tags_column")),
        cast(bool, value.get("tags_parse_json", False)),
        cast(str | None, value.get("split_column")),
        cast(str | None, value.get("metadata_column")),
        cast(bool, value.get("metadata_parse_json", False)),
    )


def project_import_mapping(mapping_source: str) -> MappingProjectionV1:
    if type(mapping_source) is not str:
        raise ValueError("invalid_mapping_source")
    digest = _source_hash(mapping_source)
    if digest is None:
        return MappingProjectionV1(1, mapping_source, None, None, "invalid_unicode", ())
    try:
        value = JsonDocument(mapping_source).value
    except JsonError as error:
        return MappingProjectionV1(1, mapping_source, digest, None, error.code, ())
    if type(value) is not dict:
        return MappingProjectionV1(1, mapping_source, digest, None, "unsupported_mapping_shape", ())
    raw = cast(dict[str, JsonValue], value)
    form = _mapping_form(raw)
    if form is None:
        return MappingProjectionV1(1, mapping_source, digest, None, "unsupported_mapping_shape", ())
    try:
        ImportMapping.model_validate_json(mapping_source)
    except ValidationError as error:
        advice = _notices(error)
    else:
        advice = ()
    return MappingProjectionV1(1, mapping_source, digest, form, None, advice)


def transform_import_mapping(
    mapping_source: str, edit: MappingEditV1
) -> MappingTransformV1:
    projection = project_import_mapping(mapping_source)
    if projection.form is None or projection.source_hash is None:
        raise ValueError("mapping_form_unavailable")
    try:
        admitted = _MAPPING_EDIT.validate_python(edit)
        value = JsonDocument(mapping_source).value
        if type(value) is not dict:
            raise ValueError("mapping_form_unavailable")
        transformed = cast(dict[str, JsonValue], deepcopy(value))
        if isinstance(admitted, SetMappingField):
            transformed[admitted.field] = cast(JsonValue, admitted.value)
        elif isinstance(admitted, ReplaceMappingFields):
            transformed["fields"] = [
                {"source": item.source, "target": item.target, "parse_json": item.parse_json}
                for item in admitted.fields
            ]
        elif isinstance(admitted, ReplaceOptionAliases):
            transformed["option_aliases"] = [
                {"value": item.value, "option_id": item.option_id}
                for item in admitted.option_aliases
            ]
        else:
            raise ValueError("unsupported_mapping_edit")
        output = dump_json(transformed)
    except (JsonError, ValidationError, ValueError, TypeError) as error:
        raise ValueError("invalid_mapping_edit") from error
    result = project_import_mapping(output)
    digest = result.source_hash
    if digest is None:
        raise ValueError("invalid_mapping_edit")
    advice = result.validation_advice
    return MappingTransformV1(1, projection.source_hash, output, digest, result, advice)
