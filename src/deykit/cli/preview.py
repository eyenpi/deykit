"""Filesystem adapters for pathless application preview admission."""

from pathlib import Path

from deykit.application.imports import ImportPreview
from deykit.application.preview_documents import decode_import_preview, decode_split_preview
from deykit.application.splits import SplitPreview


def import_preview(path: Path, dataset_id: str) -> ImportPreview:
    return decode_import_preview(path.read_bytes(), dataset_id)


def split_preview(path: Path, dataset_id: str) -> SplitPreview:
    return decode_split_preview(path.read_bytes(), dataset_id)
