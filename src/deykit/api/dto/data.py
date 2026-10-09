"""Typed dataset, case, import, and split transport records."""

from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator, model_validator

from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.json_value import JsonSource
from deykit.contracts.records import CaseRecord, DatasetRecord, DatasetSnapshot
from deykit.domain.import_mapping import ImportMapping
from deykit.domain.splits import DEFAULT_RATIOS

from .common import CountText, Mutation, ResponseRecord, VersionRequest

SeedText = Annotated[str, StringConstraints(strict=True, pattern=r"^(?:0|-?[1-9][0-9]*)$")]


def _array_tuple(value: object) -> object:
    if type(value) is list:
        return tuple(_array_tuple(item) for item in value)
    return value


class DatasetDTO(ResponseRecord):
    record: DatasetRecord
    etag: ContentHash


class DatasetPageDTO(ResponseRecord):
    items: tuple[DatasetDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class DatasetCreateRequest(Mutation):
    name: Annotated[str, StringConstraints(strict=True, min_length=1)]
    metadata_source: JsonSource = "{}"
    dataset_id: ResourceId | None = None


class DatasetPatchRequest(Mutation):
    expected_etag: ContentHash
    name: Annotated[str, StringConstraints(strict=True, min_length=1)] | None = None
    metadata_source: JsonSource | None = None


class DatasetChangeRequest(Mutation):
    expected_etag: ContentHash


class CaseDTO(ResponseRecord):
    record: CaseRecord
    etag: ContentHash


class CasePageDTO(ResponseRecord):
    items: tuple[CaseDTO, ...]
    total: CountText
    next_cursor: ResourceId | None
    dataset_etag: ContentHash


class CaseReadDTO(ResponseRecord):
    case: CaseDTO
    dataset_etag: ContentHash


class CaseInputRequest(Mutation):
    input_kind: Literal["text", "json"]
    input_source: JsonSource
    tags: tuple[str, ...] = ()
    split: Literal["development", "calibration", "test"] = "development"
    group_id: ResourceId | None = None
    derived_from: tuple[ResourceId, ...] = ()
    metadata_source: JsonSource = "{}"
    expected_dataset_etag: ContentHash
    case_id: ResourceId | None = None

    @field_validator("tags", "derived_from", mode="before")
    @classmethod
    def json_arrays(cls, value: object) -> object:
        return _array_tuple(value)


class CaseEditRequest(Mutation):
    expected_dataset_etag: ContentHash
    expected_case_etag: ContentHash
    input_kind: Literal["text", "json"]
    input_source: JsonSource
    tags: tuple[str, ...] = ()
    split: Literal["development", "calibration", "test"] = "development"
    group_id: ResourceId | None = None
    derived_from: tuple[ResourceId, ...] = ()
    metadata_source: JsonSource = "{}"

    @field_validator("tags", "derived_from", mode="before")
    @classmethod
    def json_arrays(cls, value: object) -> object:
        return _array_tuple(value)


class CaseChangeRequest(Mutation):
    expected_dataset_etag: ContentHash
    expected_case_etag: ContentHash


class CaseMutationDTO(ResponseRecord):
    dataset: DatasetDTO
    case: CaseDTO | None
    cleared_label_ids: tuple[ResourceId, ...]
    replayed: bool


class ImportPreviewRequest(VersionRequest):
    source_text: Annotated[str, StringConstraints(strict=True)]
    format: Literal["csv", "jsonl"]
    mapping_source: JsonSource
    decision_id: ResourceId | None = None
    decision_selector: ResourceId = "draft"


class ServiceErrorDTO(ResponseRecord):
    code: str
    message: str
    resource_id: ResourceId | None = None
    row: CountText | None = None
    reason: ResourceId | None = None


class ImportRowDTO(ResponseRecord):
    row: CountText
    source_line: CountText
    case: CaseRecord | None
    acceptable_option_ids: tuple[ResourceId, ...]
    errors: tuple[ServiceErrorDTO, ...]
    duplicate_input_ids: tuple[ResourceId, ...]


class ImportPreviewRecordDTO(ResponseRecord):
    dataset_id: ResourceId
    dataset_etag: ContentHash
    source_text: str
    source_hash: ContentHash
    format: Literal["csv", "jsonl"]
    mapping: ImportMapping
    mapping_hash: ContentHash
    decision_id: ResourceId | None
    decision_selector: ResourceId
    context_hash: ContentHash
    question_id: ResourceId | None
    rows: tuple[ImportRowDTO, ...]
    preview_hash: ContentHash


class ImportPreviewDTO(ResponseRecord):
    preview: ImportPreviewRecordDTO
    would_import: CountText
    preview_document_source: JsonSource


class ImportCommitRequest(Mutation):
    preview_document_source: JsonSource
    skip_invalid: bool = False


class ImportCommitDTO(ResponseRecord):
    dataset: DatasetDTO
    imported_case_ids: tuple[ResourceId, ...]
    exclusions: tuple[ImportRowDTO, ...]
    duplicate_rows: tuple[ImportRowDTO, ...]
    replayed: bool


class SplitPreviewRequest(VersionRequest):
    seed: SeedText = "0"
    ratios_source: JsonSource = DEFAULT_RATIOS
    assignments: (
        tuple[tuple[ResourceId, Literal["development", "calibration", "test"]], ...] | None
    ) = None

    @field_validator("assignments", mode="before")
    @classmethod
    def json_arrays(cls, value: object) -> object:
        return _array_tuple(value)

    @model_validator(mode="after")
    def one_split_mode(self) -> "SplitPreviewRequest":
        if self.assignments is not None and {"seed", "ratios_source"}.intersection(
            self.model_fields_set
        ):
            raise ValueError("explicit_assignments_exclude_seed_and_ratios")
        return self


class SplitPreviewRecordDTO(ResponseRecord):
    dataset_id: ResourceId
    dataset_etag: ContentHash
    input_identity: ContentHash
    algorithm: str
    seed: SeedText | None
    ratios_source: JsonSource | None
    assignments: tuple[tuple[ResourceId, Literal["development", "calibration", "test"]], ...]
    groups: tuple[tuple[ResourceId, ...], ...]
    counts: tuple[tuple[Literal["development", "calibration", "test"], CountText], ...]


class SplitPreviewDTO(ResponseRecord):
    preview: SplitPreviewRecordDTO
    preview_document_source: JsonSource


class SplitCommitRequest(Mutation):
    preview_document_source: JsonSource


class SplitCommitDTO(ResponseRecord):
    dataset: DatasetDTO
    snapshot: DatasetSnapshot
    replayed: bool
