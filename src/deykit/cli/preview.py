"""Strict admission of an exported CLI preview for an explicit later commit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportPreview
from deykit.application.splits import SplitPreview
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import RECORD_LIMITS, parse_json


@dataclass(frozen=True)
class _ImportData:
    preview: ImportPreview
    would_import: int


@dataclass(frozen=True)
class _SplitData:
    preview: SplitPreview


@dataclass(frozen=True)
class _ImportEnvelope:
    schema_version: Literal[1]
    data: _ImportData
    warnings: tuple[()]


@dataclass(frozen=True)
class _SplitEnvelope:
    schema_version: Literal[1]
    data: _SplitData
    warnings: tuple[()]


def _invalid() -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason="invalid_preview_file"))


def _load(path: Path, *, import_kind: bool) -> _ImportEnvelope | _SplitEnvelope:
    """Accept only the versioned dry-run envelope, never an arbitrary DTO fragment."""
    source = path.read_bytes()
    value = parse_json(source, RECORD_LIMITS)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "data", "warnings"}
        or value["warnings"] != []
        or not isinstance(value["data"], dict)
        or set(value["data"]) != ({"preview", "would_import"} if import_kind else {"preview"})
    ):
        raise _invalid()
    try:
        if import_kind:
            return TypeAdapter(_ImportEnvelope).validate_json(source, strict=True)
        return TypeAdapter(_SplitEnvelope).validate_json(source, strict=True)
    except (ValidationError, ValueError, TypeError):
        raise _invalid() from None


def import_preview(path: Path, dataset_id: str) -> ImportPreview:
    envelope = _load(path, import_kind=True)
    if not isinstance(envelope, _ImportEnvelope):
        raise _invalid()
    preview = envelope.data.preview
    if preview.dataset_id != dataset_id or envelope.data.would_import != len(preview.valid_rows):
        raise _invalid()
    return preview


def split_preview(path: Path, dataset_id: str) -> SplitPreview:
    envelope = _load(path, import_kind=False)
    if not isinstance(envelope, _SplitEnvelope):
        raise _invalid()
    preview = envelope.data.preview
    if preview.dataset_id != dataset_id:
        raise _invalid()
    return preview
