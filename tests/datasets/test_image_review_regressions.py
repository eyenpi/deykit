"""Review regressions: identity separation and bounded, shared image admission."""

import io

import pytest
from PIL import Image

from deykit.application import images as image_admission
from deykit.application import imports as import_application
from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportService
from deykit.contracts.codec import dump_record
from deykit.contracts.images import CaseImage, ImagePreparation
from deykit.contracts.json_value import JsonDocument, bytes_hash, dump_json
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.records import CaseRecord
from deykit.domain.case_identity import case_input_hash
from deykit.domain.import_mapping import ImageField, ImportMapping
from deykit.images.local import LocalImages


def test_image_input_hash_cannot_equal_a_json_only_envelope():
    original_hash = "a" * 64
    image = CaseRecord(
        id="image",
        dataset_id="data",
        input_kind="json",
        input_source='{"text":"red"}',
        images=(CaseImage(name="product", asset_id="image-fixture", source_hash=original_hash),),
    )
    plain = CaseRecord(
        id="plain",
        dataset_id="data",
        input_kind="json",
        input_source=dump_json({"input": {"text": "red"}, "images": [["product", original_hash]]}),
    )
    assert case_input_hash(image) != case_input_hash(plain)
    assert case_input_hash(plain) == JsonDocument(plain.input_source).content_hash


def assets(tmp_path):
    reader = LocalImages(tmp_path)
    values = []
    for name, color in (("red", (255, 0, 0)), ("blue", (0, 0, 255))):
        image = Image.new("RGB", (2, 1), color)
        output = io.BytesIO()
        image.save(output, format="PNG")
        (tmp_path / f"{name}.png").write_bytes(output.getvalue())
        values.append(reader.prepare(f"{name}.png", ImagePreparation()))
    return reader, values


def test_import_bounds_unique_encoded_assets_in_preview_and_commit(project, tmp_path, monkeypatch):
    source, datasets, imports, _ = project
    reader, (red, blue) = assets(tmp_path)
    service = ImportService(source, imports.clock, images=reader)
    mapping = ImportMapping(
        input_kind="text",
        input_column="text",
        id_column="id",
        images=(ImageField(source="photo", name="product"),),
    )
    rows = (
        '{"id":"red","text":"red","photo":"red.png"}\n'
        '{"id":"blue","text":"blue","photo":"blue.png"}\n'
    )
    preview = service.preview("data", rows, format="jsonl", mapping=mapping)
    monkeypatch.setattr(
        import_application, "MAX_IMPORT_IMAGE_BYTES", len(red.source_base64), raising=False
    )
    for work in (
        lambda: service.preview("data", rows, format="jsonl", mapping=mapping),
        lambda: service.commit(preview, operation_id="over-budget"),
    ):
        with pytest.raises(ServiceFailure) as error:
            work()
        assert error.value.error.reason == "import_image_resource_limit"
    assert not source.list_ids("image_assets") and datasets.list_cases("data").total == 0
    duplicate = rows.replace('"blue.png"', '"red.png"')
    allowed = service.preview("data", duplicate, format="jsonl", mapping=mapping)
    assert len(allowed.valid_rows) == 2
    aliases = mapping.model_copy(
        update={
            "images": (
                ImageField(source="photo", name="product"),
                ImageField(source="photo", name="detail"),
            )
        }
    )
    shared = service.preview("data", duplicate, format="jsonl", mapping=aliases)
    assert len(shared.rows[0].case.images) == 2 and len(shared.rows[0].assets) == 1
    service.commit(allowed, operation_id="shared-within-budget")
    assert source.list_ids("image_assets") == (red.id,)


def test_shared_asset_is_admitted_once_per_check(tmp_path, monkeypatch):
    _, (asset, _) = assets(tmp_path)
    body = dump_record(asset)
    stored = StoredRecord(ResourceKey("image_assets", asset.id), body, bytes_hash(body))
    cases = tuple(
        CaseRecord(
            id=f"case-{i}",
            dataset_id="data",
            input_kind="text",
            input_source='"red"',
            images=(
                CaseImage(name="product", asset_id=asset.id, source_hash=asset.source.content_hash),
            ),
        )
        for i in range(4)
    )
    calls = []
    decode = image_admission.decoded

    def observed(kind, record):
        calls.append(record.key)
        return decode(kind, record)

    monkeypatch.setattr(image_admission, "decoded", observed)
    image_admission.check_case_assets(cases, (stored,))
    assert calls == [stored.key]


def test_admission_cache_evicts_and_never_crosses_captured_views(tmp_path, monkeypatch):
    _, (red, blue) = assets(tmp_path)
    records = {}
    cases = []
    for index, asset in enumerate((red, blue)):
        body = dump_record(asset)
        key = ResourceKey("image_assets", asset.id)
        records[key] = StoredRecord(key, body, bytes_hash(body))
        cases.append(
            CaseRecord(
                id=f"case-{index}",
                dataset_id="data",
                input_kind="text",
                input_source='"red"',
                images=(
                    CaseImage(
                        name="product", asset_id=asset.id, source_hash=asset.source.content_hash
                    ),
                ),
            )
        )
    monkeypatch.setattr(
        image_admission,
        "MAX_ADMITTED_IMAGE_BYTES",
        max(len(record.body) for record in records.values()),
    )
    calls = []
    decode = image_admission.decoded

    def observed(kind, record):
        calls.append(record.key)
        return decode(kind, record)

    monkeypatch.setattr(image_admission, "decoded", observed)
    view = image_admission.ImageAssets(records)
    view.for_case(cases[0])
    view.for_case(cases[0])
    view.for_case(cases[1])
    view.for_case(cases[0])
    assert calls == [ResourceKey("image_assets", asset.id) for asset in (red, blue, red)]
    key = ResourceKey("image_assets", red.id)
    records[key] = StoredRecord(key, b"{}", bytes_hash(b"{}"))
    assert view.for_case(cases[0])["product"] == red
    with pytest.raises(ServiceFailure):
        image_admission.ImageAssets(records).for_case(cases[0])
