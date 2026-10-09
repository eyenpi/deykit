"""Focused transport boundaries for DATA routes."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from deykit.api.dto.data import (
    CaseInputRequest,
    DatasetPatchRequest,
    SplitPreviewRequest,
)
from deykit.api.routes.data import _dataset_patch_values, _seed, _split_preview
from deykit.application.errors import ServiceFailure
from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.imports import ImportService
from deykit.application.preview_documents import (
    decode_import_preview,
    decode_split_preview,
    encode_import_preview,
    encode_split_preview,
)
from deykit.application.splits import SplitService
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import dump_json, parse_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import ProjectRecord
from deykit.domain.import_mapping import ImportMapping
from deykit.domain.splits import DEFAULT_RATIOS
from deykit.storage import FileProjectSource

STAMP = "2026-10-09T12:00:00Z"


class _Clock:
    def utc_now(self) -> str:
        return STAMP

    def monotonic(self) -> float:
        return 0.0


def _project_source(tmp_path: Path):
    source = FileProjectSource(tmp_path / "project", create=True)
    source.commit(
        "project-create",
        (
            SourceChange(
                ResourceKey("project", "project-1"),
                dump_record(ProjectRecord(id="project-1", name="Test", created_at=STAMP)),
                None,
            ),
        ),
    )
    clock = _Clock()
    def id_factory() -> str:
        return "generated-1"

    datasets = DatasetService(source, clock, id_factory)
    dataset = datasets.create("Dataset", dataset_id="dataset-1", operation_id="dataset-create")
    input_source = '{"fraction":0.1234567890123456789012345,"large":9007199254740993}'
    case = datasets.add_case(
        "dataset-1",
        CaseInput(input_kind="json", input_source=input_source),
        expected_dataset_etag=dataset.etag,
        operation_id="case-create",
        case_id="case-existing",
    )
    return source, clock, id_factory, datasets, case.dataset


def test_case_input_keeps_large_integer_and_fraction_as_original_source() -> None:
    input_source = '{"large":9007199254740993,"fraction":0.1234567890123456789012345}'
    metadata_source = '{"n":9007199254740993,"ratio":0.1234567890123456789012345}'

    request = CaseInputRequest(
        schema_version=1,
        operation_id="case-add",
        expected_dataset_etag="a" * 64,
        input_kind="json",
        input_source=input_source,
        metadata_source=metadata_source,
    )

    assert request.input_source == input_source
    assert request.metadata_source == metadata_source
    assert request.model_dump(mode="json")["input_source"] == input_source
    assert request.model_dump(mode="json")["metadata_source"] == metadata_source


def test_dataset_patch_distinguishes_omitted_from_explicit_null() -> None:
    omitted = DatasetPatchRequest(
        schema_version=1, operation_id="dataset-patch", expected_etag="a" * 64
    )
    explicit_null = DatasetPatchRequest(
        schema_version=1,
        operation_id="dataset-patch",
        expected_etag="a" * 64,
        name=None,
    )

    with pytest.raises(ServiceFailure):
        _dataset_patch_values(omitted)
    with pytest.raises(ServiceFailure):
        _dataset_patch_values(explicit_null)

    updated = DatasetPatchRequest(
        schema_version=1,
        operation_id="dataset-patch",
        expected_etag="a" * 64,
        metadata_source='{"large":9007199254740993}',
    )
    assert _dataset_patch_values(updated) == {
        "metadata_source": '{"large":9007199254740993}'
    }


def test_seed_is_signed_64_bit_decimal_text() -> None:
    assert _seed("-9223372036854775808") == -(2**63)
    assert _seed("9223372036854775807") == 2**63 - 1

    for value in ("+1", "01", "-0", "9223372036854775808", "-9223372036854775809"):
        with pytest.raises(ServiceFailure):
            _seed(value)

    with pytest.raises(ValidationError):
        SplitPreviewRequest(schema_version=1, seed=1)


def test_split_request_requires_assignments_without_seeded_fields() -> None:
    with pytest.raises(ValidationError):
        SplitPreviewRequest(schema_version=1, seed="0", assignments=(("case-a", "test"),))

    request = SplitPreviewRequest.model_validate(
        {"schema_version": 1, "assignments": [["case-a", "test"]]}
    )
    assert request.assignments == (("case-a", "test"),)


def test_case_transport_admits_json_arrays_as_structural_tuples() -> None:
    request = CaseInputRequest.model_validate(
        {
            "schema_version": 1,
            "operation_id": "case-add",
            "expected_dataset_etag": "a" * 64,
            "input_kind": "text",
            "input_source": '"decision input"',
            "tags": ["gold", "regression"],
            "derived_from": ["case-original"],
        }
    )

    assert request.tags == ("gold", "regression")
    assert request.derived_from == ("case-original",)


def test_import_preview_opaque_document_round_trips_exact_case_sources(tmp_path: Path) -> None:
    source, clock, id_factory, _, dataset = _project_source(tmp_path)
    try:
        raw_import = (
            '{"payload":{"fraction":0.1234567890123456789012345,'
            '"large":9007199254740993}}\n'
        )
        preview = ImportService(source, clock, id_factory).preview(
            dataset.record.id,
            raw_import,
            format="jsonl",
            mapping=ImportMapping(input_kind="json", input_column="payload"),
        )

        document_source = encode_import_preview(preview)
        decoded = decode_import_preview(document_source, dataset.record.id)

        assert decoded == preview
        case = decoded.rows[0].case
        expected_case = preview.rows[0].case
        assert case is not None
        assert expected_case is not None
        assert case.input_source == expected_case.input_source
        values = parse_json(case.input_source)
        assert isinstance(values, dict)
        assert values["large"] == 9007199254740993
        assert values["fraction"] == parse_json("0.1234567890123456789012345")
    finally:
        source.close()


def test_import_preview_rejects_tampered_import_count(tmp_path: Path) -> None:
    source, clock, id_factory, _, dataset = _project_source(tmp_path)
    try:
        preview = ImportService(source, clock, id_factory).preview(
            dataset.record.id,
            '{"payload":{"large":9007199254740993}}\n',
            format="jsonl",
            mapping=ImportMapping(input_kind="json", input_column="payload"),
        )
        document = parse_json(encode_import_preview(preview))
        assert isinstance(document, dict)
        data = document["data"]
        assert isinstance(data, dict)
        data["would_import"] = 0

        with pytest.raises(ServiceFailure):
            decode_import_preview(dump_json(document), dataset.record.id)
    finally:
        source.close()


def test_split_preview_source_round_trip_keeps_seed_exact_and_api_uses_text(
    tmp_path: Path,
) -> None:
    source, clock, id_factory, _, dataset = _project_source(tmp_path)
    try:
        preview = SplitService(source, clock, id_factory).preview(
            dataset.record.id,
            seed=9007199254740993,
            ratios_source=DEFAULT_RATIOS,
        )

        document_source = encode_split_preview(preview)
        decoded = decode_split_preview(document_source, dataset.record.id)

        assert decoded == preview
        assert _split_preview(preview).preview.seed == "9007199254740993"
        assert _split_preview(preview).preview_document_source == document_source
    finally:
        source.close()
