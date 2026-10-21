"""Observable asset preparation, reviewed import and portable identity contracts."""

import io
import os
import shutil

import pytest
from PIL import Image

from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.images import ImageAsset, ImagePreparation
from deykit.contracts.ports import ResourceKey
from deykit.domain.import_mapping import ImageField, ImportMapping
from deykit.images.local import LocalImages
from deykit.storage import FileProjectSource


def png():
    image = Image.new("RGB", (2, 1))
    image.putdata([(255, 0, 0), (0, 0, 255)])
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_explicit_padding_pixels_and_preserved_original_bytes(tmp_path):
    original = png()
    (tmp_path / "product.png").write_bytes(original)
    images = LocalImages(tmp_path)
    unchanged = images.prepare("product.png", ImagePreparation())
    assert unchanged.source_bytes() == unchanged.prepared_bytes() == original
    assert unchanged.source == unchanged.prepared
    settings = ImagePreparation(mode="pad", min_width=5, min_height=4, background=(0, 255, 0))
    padded = images.prepare("product.png", settings)
    assert padded.source_bytes() == original
    assert padded.prepared.width == 5 and padded.prepared.height == 4
    assert padded.source.content_hash != padded.prepared.content_hash
    assert images.prepare("product.png", settings) == padded
    with Image.open(io.BytesIO(padded.prepared_bytes())) as image:
        expected = [(0, 255, 0)] * 20
        expected[6:8] = [(255, 0, 0), (0, 0, 255)]
        assert list(image.get_flattened_data()) == expected
    assert load_record(ImageAsset, dump_record(padded)) == padded


def test_reviewed_image_import_rechecks_files_and_survives_copy(project, tmp_path):
    source, datasets, imports, _ = project
    root = tmp_path / "images"
    root.mkdir()
    (root / "product.png").write_bytes(png())
    service = ImportService(source, imports.clock, images=LocalImages(root))
    mapping = ImportMapping(
        input_kind="json",
        fields=({"source": "text", "target": "text"},),
        id_column="id",
        expected_column="expected",
        images=(ImageField(source="file", name="product"),),
    )
    preview = service.preview(
        "data",
        '{"id":"p1","text":"red","file":"product.png","expected":"A"}\n',
        format="jsonl",
        mapping=mapping,
        decision_id="decision",
    )
    assert not preview.exclusions
    case = preview.rows[0].case
    assert case.input_source == '{"text":"red"}'
    assert case.images[0].name == "product"
    assert preview.rows[0].assets[0].preparation.mode == "preserve"
    assert not source.list_ids("image_assets")
    (root / "product.png").write_bytes(b"changed")
    with pytest.raises(ServiceFailure):
        service.commit(preview, operation_id="import-image")
    assert not datasets.list_cases("data").items
    (root / "product.png").write_bytes(png())
    result = service.commit(preview, operation_id="import-image")
    assert result.imported_case_ids == ("p1",)
    (root / "product.png").unlink()
    assert service.commit(preview, operation_id="import-image").replayed
    asset_id = case.images[0].asset_id
    saved = source.read(ResourceKey("image_assets", asset_id))
    assert load_record(ImageAsset, saved.body).source_bytes() == png()
    copied = tmp_path / "copy"
    shutil.copytree(source.root, copied)
    with FileProjectSource(copied) as other:
        assert other.read(ResourceKey("image_assets", asset_id)).body == saved.body


@pytest.mark.parametrize("path", ["../product.png", "/product.png", "https://example.org/x.png"])
def test_local_assets_cannot_escape_explicit_root(tmp_path, path):
    with pytest.raises(ValueError):
        LocalImages(tmp_path).prepare(path, ImagePreparation())


def test_images_cannot_alias_metadata_or_model_text_columns():
    with pytest.raises(ValueError):
        ImportMapping(
            input_kind="text",
            input_column="input",
            images=(ImageField(source="input", name="product"),),
        )


def test_fractional_dimensions_and_implicit_transformations_rejected():
    with pytest.raises(ValueError):
        ImagePreparation(mode="preserve", min_width=100)
    with pytest.raises(ValueError):
        ImagePreparation(mode="pad", min_width=100.5, min_height=100)


@pytest.mark.skipif(
    os.name == "nt", reason="Windows link privileges vary; SafeFiles has native coverage"
)
def test_image_file_and_directory_symlinks_are_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "photo.png").write_bytes(png())
    (tmp_path / "photo.png").symlink_to(actual / "photo.png")
    (tmp_path / "linked").symlink_to(actual, target_is_directory=True)
    for path in ("photo.png", "linked/photo.png"):
        with pytest.raises(ValueError):
            LocalImages(tmp_path).prepare(path, ImagePreparation())
