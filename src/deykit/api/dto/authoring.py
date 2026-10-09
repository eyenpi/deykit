"""Decision and exact-source authoring transport records."""

from typing import Annotated, Literal

from pydantic import StringConstraints

from deykit.application.authoring_views import (
    EditorEditV1,
    EditorTransformV1,
    MappingEditV1,
)
from deykit.application.definitions import IncompatibleReference
from deykit.contracts.identities import ResourceId
from deykit.contracts.records import (
    ChoiceDefinition,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
)

from .common import CountText, ETag, Mutation, ResponseRecord, Versioned, VersionRequest


class DecisionDTO(ResponseRecord):
    decision: Versioned[DecisionRecord]
    draft: Versioned[DecisionDraft]


class DecisionPageDTO(ResponseRecord):
    items: tuple[DecisionDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class RevisionDTO(ResponseRecord):
    revision: Versioned[DecisionRevision]


class RevisionPageDTO(ResponseRecord):
    items: tuple[RevisionDTO, ...]
    total: CountText
    next_cursor: ResourceId | None


class DecisionCreateRequest(Mutation):
    decision_id: ResourceId
    name: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    editor_source: str


class DraftRequest(Mutation):
    editor_source: str
    expected_etag: ETag


class SaveRevisionRequest(Mutation):
    expected_draft_etag: ETag
    expected_decision_etag: ETag
    note: str = ""


class RenameDecisionRequest(Mutation):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    expected_etag: ETag


class DecisionETagRequest(Mutation):
    expected_etag: ETag


class RestoreRevisionRequest(Mutation):
    revision_id: ResourceId
    expected_draft_etag: ETag


class SelectionRequest(VersionRequest):
    input_source: str


class EditorProjectionRequest(VersionRequest):
    editor_source: str


class EditorTransformRequest(VersionRequest):
    editor_source: str
    edit: EditorEditV1
    expected_draft_etag: ETag


class SchemaProjectionRequest(VersionRequest):
    schema_source: str | None


class CaseInputProjectionRequest(VersionRequest):
    input_kind: Literal["text", "json"]
    input_source: str


class TextInputRequest(VersionRequest):
    text_value: str


class MappingProjectionRequest(VersionRequest):
    mapping_source: str


class MappingTransformRequest(VersionRequest):
    mapping_source: str
    edit: MappingEditV1


class DecisionSummaryDTO(ResponseRecord):
    id: ResourceId
    name: str
    archived: bool
    latest_revision_id: ResourceId | None
    decision_etag: ETag
    draft_etag: ETag


class RevisionSummaryDTO(ResponseRecord):
    id: ResourceId
    decision_id: ResourceId
    content_hash: str
    created_at: str
    note: str
    etag: ETag


class ValidationDTO(ResponseRecord):
    definition: ChoiceDefinition
    content_hash: str


class SelectionDTO(ResponseRecord):
    input_source: str
    content_hash: str


class DefinitionDiffDTO(ResponseRecord):
    before_hash: str
    after_hash: str
    input_changed: bool
    question_changed: bool
    option_order_changed: bool
    added_option_ids: tuple[ResourceId, ...]
    removed_option_ids: tuple[ResourceId, ...]
    changed_option_ids: tuple[ResourceId, ...]
    incompatible_references: tuple[IncompatibleReference, ...]


class DraftTransformReviewDTO(ResponseRecord):
    transform: EditorTransformV1
    incompatible_references: tuple[IncompatibleReference, ...] | None
