"""Public hashes provide identity, not authentication of an import proposal."""

import traceback
import warnings
from dataclasses import replace

import pytest

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportRow, _preview_hash
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import semantic_hash
from deykit.contracts.records import CaseRecord
from deykit.domain.import_mapping import ImportMapping, InputField

SENTINEL = "PRIVATE_INPUT_SENTINEL"


def valid_preview(imports):
    return imports.preview(
        "data",
        '{"id":"case","text":"A","expected":"A"}',
        format="jsonl",
        mapping=ImportMapping(
            input_kind="json",
            fields=(InputField(source="text", target="text"),),
            id_column="id",
            expected_column="expected",
        ),
        decision_id="decision",
    )


def assert_safe_failure(storage, capsys, request):
    before = storage.capture_snapshot()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        with pytest.raises(ServiceFailure) as failure:
            request()
    assert captured == []
    assert capsys.readouterr().err == ""
    assert SENTINEL not in "".join(traceback.format_exception(failure.value))
    assert storage.capture_snapshot() == before
    return failure.value.error


def test_forged_mapping_with_recomputed_public_hashes_cannot_copy_label_into_input(project, capsys):
    storage, _, imports, _ = project
    preview = valid_preview(imports)
    forged_mapping = preview.mapping.model_copy(
        update={"fields": (InputField(source="expected", target="text"),)}
    )
    forged = replace(
        preview,
        mapping=forged_mapping,
        mapping_hash=semantic_hash(forged_mapping.model_dump(mode="json")),
    )
    forged = replace(forged, preview_hash=_preview_hash(forged))
    # Hashes and resulting row values all agree, but column separation is invalid.
    assert forged.rows[0].case.input_source == '{"text":"A"}'
    error = assert_safe_failure(
        storage, capsys, lambda: imports.commit(forged, operation_id="forged")
    )
    assert error.reason == "invalid_import_mapping"


@pytest.mark.parametrize("operation", ["preview", "commit"])
@pytest.mark.parametrize(
    "malformation",
    ["copy", "construct", "nested_copy", "nested_construct", "raw_dict", "surrogate"],
)
def test_untrusted_mapping_is_validated_before_any_serializer(
    project, capsys, operation, malformation
):
    storage, _, imports, _ = project
    preview = valid_preview(imports)
    mapping = preview.mapping
    if malformation == "copy":
        mapping = mapping.model_copy(update={"fields": (SENTINEL,)})
    elif malformation == "construct":
        mapping = ImportMapping.model_construct(input_kind="json", fields=(SENTINEL,))
    elif malformation == "nested_copy":
        mapping = mapping.model_copy(
            update={"fields": (mapping.fields[0].model_copy(update={"parse_json": SENTINEL}),)}
        )
    elif malformation == "nested_construct":
        mapping = mapping.model_copy(
            update={"fields": (InputField.model_construct(source=SENTINEL, target=123),)}
        )
    elif malformation == "surrogate":
        mapping = mapping.model_copy(update={"id_column": chr(0xD800)})
    else:
        mapping = {"input_kind": "json", "fields": (SENTINEL,)}

    def request():
        if operation == "commit":
            return imports.commit(replace(preview, mapping=mapping), operation_id="bad")
        return imports.preview(
            "data", preview.source_text, format="jsonl", mapping=mapping, decision_id="decision"
        )

    error = assert_safe_failure(storage, capsys, request)
    assert error.reason == "invalid_import_mapping"


@pytest.mark.parametrize("source", [123, {}, [], None, bytearray(b"abc")])
def test_wrong_source_types_are_safe_at_both_parsing_boundaries(project, capsys, source):
    storage, _, imports, _ = project
    mapping = ImportMapping(input_kind="text", input_column="text")
    assert_safe_failure(
        storage, capsys, lambda: imports.preview("data", source, format="jsonl", mapping=mapping)
    )
    assert_safe_failure(storage, capsys, lambda: imports.parse_mapping(source))


@pytest.mark.parametrize(
    "malformation",
    [
        "surrogate",
        "construct",
        "tags",
        "dataset",
        "row",
        "line",
        "option",
        "error",
        "rows_type",
        "mapping_type",
        "source_type",
        "missing_attributes",
    ],
)
def test_forged_preview_nested_values_are_safe_before_hashing(project, capsys, malformation):
    storage, _, imports, _ = project
    preview = valid_preview(imports)
    row = preview.rows[0]
    if malformation == "surrogate":
        row = replace(
            row, case=row.case.model_copy(update={"input_source": '"' + chr(0xD800) + '"'})
        )
    elif malformation == "construct":
        row = replace(
            row,
            case=CaseRecord.model_construct(
                id="case", dataset_id="data", input_kind="json", input_source=SENTINEL
            ),
        )
    elif malformation == "tags":
        row = replace(row, case=row.case.model_copy(update={"tags": (object(),)}))
    elif malformation == "dataset":
        row = replace(row, case=row.case.model_copy(update={"dataset_id": "other"}))
    elif malformation == "row":
        row = replace(row, row=True)
    elif malformation == "line":
        row = replace(row, source_line=SENTINEL)
    elif malformation == "option":
        row = replace(row, acceptable_option_ids=(object(),))
    elif malformation == "error":
        row = replace(row, errors=(ServiceError.model_construct(code=SENTINEL),))
    elif malformation == "rows_type":
        preview = replace(preview, rows=SENTINEL)
    elif malformation == "mapping_type":
        preview = replace(preview, mapping=123)
    elif malformation == "source_type":
        preview = replace(preview, source_text=123)
    else:
        row = object.__new__(ImportRow)
    if malformation not in ("rows_type", "mapping_type", "source_type"):
        preview = replace(preview, rows=(row,))
    assert_safe_failure(storage, capsys, lambda: imports.commit(preview, operation_id="bad"))


@pytest.mark.parametrize("value", [None, {}, 123, object()])
def test_raw_wrong_preview_types_are_safe(project, capsys, value):
    storage, _, imports, _ = project
    assert_safe_failure(storage, capsys, lambda: imports.commit(value, operation_id="bad"))


def test_manual_case_uses_same_pre_serialization_model_validation(project, capsys):
    storage, datasets, _, dataset = project
    value = CaseInput.model_construct(
        input_kind="text", input_source='"text"', tags=(SENTINEL, object())
    )
    assert_safe_failure(
        storage,
        capsys,
        lambda: datasets.add_case(
            "data", value, expected_dataset_etag=dataset.etag, operation_id="bad"
        ),
    )
