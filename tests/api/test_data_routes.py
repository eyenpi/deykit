"""Focused transport boundaries for DATA routes."""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from threading import local
from types import SimpleNamespace
from typing import NoReturn

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from pydantic import ValidationError

from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.dto.data import (
    CaseInputRequest,
    DatasetPatchRequest,
    SplitPreviewRequest,
)
from deykit.api.routes.data import (
    _dataset_patch_values,
    _seed,
    _split_preview,
)
from deykit.api.routes.data import (
    register as register_data_routes,
)
from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.errors import ServiceFailure
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
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource

STAMP = "2026-10-09T12:00:00Z"


class _Clock:
    def utc_now(self) -> str:
        return STAMP

    def monotonic(self) -> float:
        return 0.0


class _EpochSource:
    def __init__(self, source: FileProjectSource) -> None:
        self.source = source
        self.local = local()
        self.next_epoch = 0
        self.reads: list[tuple[str, str, int, str | None]] = []

    @contextmanager
    def consistent_read(self):
        depth = getattr(self.local, "depth", 0)
        with self.source.consistent_read():
            if depth == 0:
                self.next_epoch += 1
                self.local.epoch = self.next_epoch
            self.local.depth = depth + 1
            try:
                yield self
            finally:
                self.local.depth = depth

    def read(self, key):
        result = self.source.read(key)
        self.reads.append(
            (
                key.collection,
                key.resource_id,
                getattr(self.local, "epoch", 0),
                result.etag if result else None,
            )
        )
        return result

    def __getattr__(self, name):
        return getattr(self.source, name)


class _CountingWorkers:
    def __init__(self) -> None:
        self.calls = 0

    async def run_sync(self, function, *args, **kwargs):
        self.calls += 1
        return function(*args, **kwargs)


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
    assert _dataset_patch_values(updated) == {"metadata_source": '{"large":9007199254740993}'}


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
            '{"payload":{"fraction":0.1234567890123456789012345,"large":9007199254740993}}\n'
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


@pytest.mark.parametrize(
    "path",
    (
        "/projects/registration-1/datasets/dataset-1/cases/case-existing",
        "/projects/registration-1/datasets/dataset-1/cases?limit=50",
    ),
)
def test_case_read_and_page_capture_etags_in_one_worker_epoch(tmp_path: Path, path: str) -> None:
    source, clock, id_factory, _, _ = _project_source(tmp_path)
    epoch_source = _EpochSource(source)
    workers = _CountingWorkers()

    class Registry:
        def require(self, registration_id: str):
            assert registration_id == "registration-1"
            return SimpleNamespace(source=epoch_source)

    class Recent:
        last_warning = None

        def list(self):
            return ()

        def remember(self, path: str, project_id: str, name: str):
            return None

    provider_factory_calls = 0
    backend_factory_calls = 0

    def forbidden_provider_factory(source: ApiProjectSource) -> NoReturn:
        nonlocal provider_factory_calls
        provider_factory_calls += 1
        raise AssertionError("the case route must not construct provider services")

    def forbidden_backend_factory(source: ApiProjectSource, clock: _Clock) -> NoReturn:
        nonlocal backend_factory_calls
        backend_factory_calls += 1
        raise AssertionError("the case route must not construct provider backends")

    dependencies = ApiDependencies(
        clock=clock,
        id_factory=id_factory,
        source_factory=lambda path, create: source,
        recent_store=Recent(),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
        provider_operations_factory=forbidden_provider_factory,
        backends_factory=forbidden_backend_factory,
    )
    router = APIRouter()
    register_data_routes(router, dependencies, Registry(), workers)  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(router)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)

    try:
        response = asyncio.run(request())
        assert response.status_code == 200, response.text
        assert provider_factory_calls == 0
        assert backend_factory_calls == 0
        assert workers.calls == 1
        observed_epochs = {epoch for _, _, epoch, _ in epoch_source.reads}
        assert len(observed_epochs) == 1
        observed_etags = {
            (collection, resource_id): etag
            for collection, resource_id, _, etag in epoch_source.reads
            if etag is not None
        }
        data = response.json()["data"]
        assert data["dataset_etag"] == observed_etags[("datasets", "dataset-1")]
        if "case" in data:
            case_id = data["case"]["record"]["id"]
            assert data["case"]["etag"] == observed_etags[("cases", case_id)]
        else:
            for case in data["items"]:
                case_id = case["record"]["id"]
                assert case["etag"] == observed_etags[("cases", case_id)]
    finally:
        source.close()
