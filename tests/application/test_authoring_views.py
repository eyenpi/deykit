from decimal import Decimal

import pytest
from pydantic import ValidationError

from deykit.application.authoring_views import (
    AddOption,
    DescribeOption,
    RemoveOption,
    RemoveSchemaField,
    RenameOption,
    ReplaceSchema,
    ReorderOptions,
    SchemaField,
    SetInputKind,
    SetInstructions,
    SetMappingField,
    SetSelectedFields,
    encode_text_input,
    project_case_input,
    project_editor,
    project_import_mapping,
    project_schema,
    transform_editor,
    transform_import_mapping,
)
from deykit.contracts.json_value import JsonDocument, bytes_hash, dump_json


def editor_source(schema_source=None, *, instructions="Choose.", options=None):
    return dump_json(
        {
            "schema_version": 1,
            "input_kind": "json",
            "input_schema_source": schema_source,
            "selected_fields": ["name"],
            "questions": [
                {
                    "id": "question",
                    "kind": "choice",
                    "instructions": instructions,
                    "options": options
                    or [
                        {"id": "yes", "name": "Yes", "description": None},
                        {"id": "no", "name": "No", "description": ""},
                    ],
                }
            ],
        }
    )


def test_editor_projection_and_option_edits_preserve_identity_nulls_and_exact_schema():
    schema = '{"type":"object","properties":{"name":{"type":"string","minLength":1}}}'
    source = editor_source(schema)
    projected = project_editor(source)
    assert projected.editor_source == source
    assert projected.source_hash == bytes_hash(source.encode("utf-8"))
    assert projected.form is not None
    assert projected.form.question_id == "question"
    assert projected.form.input_schema_source == schema
    assert [item.id for item in projected.form.options] == ["yes", "no"]
    assert [item.description for item in projected.form.options] == [None, ""]

    changed = transform_editor(source, SetInstructions(kind="set_instructions", value="Pick one."))
    changed_value = JsonDocument(changed.editor_source).value
    assert changed_value["questions"][0]["instructions"] == "Pick one."
    assert changed_value["input_schema_source"] == schema
    assert [item["id"] for item in changed_value["questions"][0]["options"]] == ["yes", "no"]

    renamed = transform_editor(
        changed.editor_source, RenameOption(kind="rename_option", id="yes", name="Affirmative")
    )
    reordered = transform_editor(
        renamed.editor_source,
        ReorderOptions(kind="reorder_options", option_ids=("no", "yes")),
    )
    added = transform_editor(
        reordered.editor_source,
        AddOption(kind="add_option", id="maybe", name="Maybe", description=None),
    )
    described = transform_editor(
        added.editor_source,
        DescribeOption(kind="describe_option", id="maybe", description="Conditional"),
    )
    final_options = project_editor(described.editor_source).form.options
    assert [(item.id, item.name) for item in final_options] == [
        ("no", "No"),
        ("yes", "Affirmative"),
        ("maybe", "Maybe"),
    ]
    assert final_options[0].description == ""
    assert final_options[1].description is None
    assert final_options[2].description == "Conditional"


def test_incomplete_editor_is_form_editable_and_unavailable_sources_stay_raw():
    partial = editor_source(
        instructions="", options=[{"id": "only", "name": "", "description": None}]
    )
    projection = project_editor(partial)
    assert projection.form is not None
    assert projection.form.instructions == ""
    assert len(projection.form.options) == 1
    assert projection.validation_advice

    duplicate = '{"input_kind":"json","input_kind":"text"}'
    unavailable = project_editor(duplicate)
    assert unavailable.editor_source == duplicate
    assert unavailable.form is None
    assert unavailable.form_unavailable_reason == "duplicate_key"
    with pytest.raises(ValueError):
        transform_editor(duplicate, RemoveOption(kind="remove_option", id="yes"))


def test_common_schema_edit_keeps_advanced_exact_constraints_and_unedited_source():
    schema = (
        '{"type":"object","properties":{"name":{"type":"string","description":"Keep",'
        '"minLength":1},"score":{"type":"number","minimum":9007199254740993,'
        '"multipleOf":0.125},"fraction":{"type":"number",'
        '"maximum":0.1234567890123456789}},"required":["name"],"additionalProperties":false,'
        '"$defs":{"tag":{"type":"string"}}}'
    )
    projection = project_schema(schema)
    assert projection.schema_source == schema
    assert projection.source_hash == bytes_hash(schema.encode("utf-8"))
    assert projection.fields is not None
    score = next(item for item in projection.fields if item.name == "score")
    assert score.field_type == "number"
    assert score.advanced_keywords == ("minimum", "multipleOf")
    fraction = next(item for item in projection.fields if item.name == "fraction")
    assert fraction.advanced_keywords == ("maximum",)
    assert "additionalProperties" in projection.advanced_keywords

    source = editor_source(schema)
    unrelated = transform_editor(
        source, SetInstructions(kind="set_instructions", value="Choose a score.")
    )
    assert project_editor(unrelated.editor_source).form.input_schema_source == schema
    transformed = transform_editor(
        source,
        SchemaField(kind="schema_field", name="score", field_type="integer", required=True),
    )
    transformed_schema = JsonDocument(
        project_editor(transformed.editor_source).form.input_schema_source
    ).value
    score_schema = transformed_schema["properties"]["score"]
    assert score_schema["type"] == "integer"
    assert score_schema["minimum"] == Decimal("9007199254740993")
    assert score_schema["multipleOf"] == Decimal("0.125")
    assert transformed_schema["properties"]["fraction"]["maximum"] == Decimal(
        "0.1234567890123456789"
    )
    assert transformed_schema["properties"]["name"]["description"] == "Keep"
    assert transformed_schema["required"] == ["name", "score"]
    assert transformed_schema["additionalProperties"] is False
    assert transformed_schema["$defs"]["tag"]["type"] == "string"

    removed = transform_editor(
        source, RemoveSchemaField(kind="remove_schema_field", name="score")
    )
    removed_schema = JsonDocument(
        project_editor(removed.editor_source).form.input_schema_source
    ).value
    assert "score" not in removed_schema["properties"]
    assert "score" not in removed_schema["required"]
    assert removed_schema["properties"]["name"]["description"] == "Keep"

    replacement = '{"type":"object","properties":{"name":{"type":"string"}}}'
    replaced = transform_editor(
        source, ReplaceSchema(kind="replace_schema", input_schema_source=replacement)
    )
    assert project_editor(replaced.editor_source).form.input_schema_source == replacement

    selected = transform_editor(
        source, SetSelectedFields(kind="set_selected_fields", selected_fields=("score",))
    )
    assert project_editor(selected.editor_source).form.selected_fields == ("score",)
    text_input = transform_editor(
        selected.editor_source, SetInputKind(kind="set_input_kind", input_kind="text")
    )
    assert project_editor(text_input.editor_source).form.input_kind == "text"


def test_case_input_projection_and_text_encoding_keep_exact_unicode_and_newlines():
    source = ' "line one\\nline two\\nλ" '
    projected = project_case_input("text", source)
    assert projected.input_source == source
    assert projected.source_hash == bytes_hash(source.encode("utf-8"))
    assert projected.text_value == "line one\nline two\nλ"

    text = "first\nsecond\nλ"
    encoded = encode_text_input(text)
    assert JsonDocument(encoded.input_source).value == text
    assert encoded.source_hash == bytes_hash(encoded.input_source.encode("utf-8"))
    malformed = project_case_input("text", "not-json")
    assert malformed.text_value is None
    assert malformed.form_unavailable_reason == "invalid_json"

    raw_json = '{"exact":9007199254740993}'
    json_projection = project_case_input("json", raw_json)
    assert json_projection.input_source == raw_json
    assert json_projection.text_value is None
    assert json_projection.form_unavailable_reason is None


def test_mapping_transform_changes_one_column_and_retains_all_supported_values():
    source = dump_json(
        {
            "schema_version": 1,
            "input_kind": "json",
            "input_column": "payload",
            "input_parse_json": True,
            "fields": [],
            "id_column": None,
            "expected_column": "expected",
            "expected_parse_json": False,
            "option_aliases": [{"value": "Yes", "option_id": "yes"}],
            "group_column": None,
            "tags_column": None,
            "tags_parse_json": False,
            "split_column": None,
            "metadata_column": None,
            "metadata_parse_json": False,
        }
    )
    original = project_import_mapping(source)
    transformed = transform_import_mapping(
        source,
        SetMappingField(kind="set", field="tags_column", value="tags"),
    )
    before = JsonDocument(source).value
    after = JsonDocument(transformed.mapping_source).value
    assert transformed.original_source_hash == original.source_hash
    assert transformed.source_hash == bytes_hash(transformed.mapping_source.encode("utf-8"))
    assert after["tags_column"] == "tags"
    assert after["input_parse_json"] is True
    assert after["id_column"] is None
    assert after["fields"] == before["fields"]
    assert after["option_aliases"] == before["option_aliases"]
    assert transformed.projection.form.fields == ()


def test_invalid_schema_and_mapping_sources_keep_raw_text_without_a_form():
    wrong_editor_version = editor_source().replace('"schema_version":1', '"schema_version":1.0', 1)
    assert project_editor(wrong_editor_version).form is None
    exponent_editor_version = editor_source().replace('"schema_version":1', '"schema_version":1e0', 1)
    assert project_editor(exponent_editor_version).form is None

    duplicate = '{"type":"object","type":"array"}'
    schema = project_schema(duplicate)
    assert schema.schema_source == duplicate
    assert schema.fields is None
    assert schema.form_unavailable_reason == "duplicate_key"

    mapping_source = '{"input_kind":"json","input_kind":"text"}'
    mapping = project_import_mapping(mapping_source)
    assert mapping.mapping_source == mapping_source
    assert mapping.form is None
    assert mapping.form_unavailable_reason == "duplicate_key"
    with pytest.raises(ValueError):
        transform_import_mapping(
            mapping_source,
            SetMappingField(kind="set", field="input_column", value="input"),
        )
    assert project_import_mapping('{"schema_version":1.0,"input_kind":"json"}').form is None
    assert project_import_mapping('{"schema_version":1e0,"input_kind":"json"}').form is None
    with pytest.raises(ValidationError):
        SetMappingField(kind="set", field="tags_parse_json", value="true")
