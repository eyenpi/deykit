"""Strict admission of exported CLI previews for explicit later commits."""

from __future__ import annotations

from dataclasses import fields

from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportPreview, ImportRow
from deykit.application.splits import SplitPreview
from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import RECORD_LIMITS, parse_json


class _ImportData(FrozenModel):
    preview: ImportPreview
    would_import: int


class _SplitData(FrozenModel):
    preview: SplitPreview


class _ImportEnvelope(Record):
    data: _ImportData
    warnings: tuple[()]


class _SplitEnvelope(Record):
    data: _SplitData
    warnings: tuple[()]


def _invalid() -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason="invalid_preview_file"))


def _keys(value: object, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise _invalid()


def _load(source: str | bytes, *, import_kind: bool) -> _ImportEnvelope | _SplitEnvelope:
    """Require an exact versioned dry-run envelope and all DTO fields."""
    value = parse_json(source, RECORD_LIMITS)
    _keys(value, {"schema_version", "data", "warnings"})
    assert isinstance(value, dict)
    _keys(value["data"], {"preview", "would_import"} if import_kind else {"preview"})
    data = value["data"]
    assert isinstance(data, dict)
    preview = data["preview"]
    _keys(
        preview,
        {field.name for field in fields(ImportPreview if import_kind else SplitPreview)},
    )
    if import_kind:
        assert isinstance(preview, dict)
        rows = preview["rows"]
        if not isinstance(rows, list):
            raise _invalid()
        for row in rows:
            expected = {field.name for field in fields(ImportRow)}
            if isinstance(row, dict) and "assets" not in row:
                expected.remove("assets")  # Pre-image reviewed imports remain readable.
            _keys(row, expected)
    try:
        if import_kind:
            return load_record(_ImportEnvelope, source)
        return load_record(_SplitEnvelope, source)
    except ValueError:
        raise _invalid() from None


def decode_import_preview(source: str | bytes, dataset_id: str) -> ImportPreview:
    envelope = _load(source, import_kind=True)
    if not isinstance(envelope, _ImportEnvelope):
        raise _invalid()
    preview = envelope.data.preview
    if preview.dataset_id != dataset_id or envelope.data.would_import != len(preview.valid_rows):
        raise _invalid()
    return preview


def decode_split_preview(source: str | bytes, dataset_id: str) -> SplitPreview:
    envelope = _load(source, import_kind=False)
    if not isinstance(envelope, _SplitEnvelope):
        raise _invalid()
    preview = envelope.data.preview
    if preview.dataset_id != dataset_id:
        raise _invalid()
    return preview


def encode_import_preview(preview: ImportPreview) -> str:
    """Encode the exact CLI-compatible source document used by the commit endpoint."""
    envelope = _ImportEnvelope(
        data=_ImportData(preview=preview, would_import=len(preview.valid_rows)), warnings=()
    )
    return dump_record(envelope).decode("utf-8")


def encode_split_preview(preview: SplitPreview) -> str:
    """Encode the exact CLI-compatible source document used by the commit endpoint."""
    envelope = _SplitEnvelope(data=_SplitData(preview=preview), warnings=())
    return dump_record(envelope).decode("utf-8")
