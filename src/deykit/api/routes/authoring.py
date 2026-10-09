"""Decision authoring and exact-source presentation endpoints."""

from fastapi import APIRouter, Response

from deykit.api.dependencies import ApiDependencies
from deykit.application.authoring_views import (
    CaseInputProjectionV1,
    EditorProjectionV1,
    EncodedInputV1,
    MappingProjectionV1,
    MappingTransformV1,
    SchemaProjectionV1,
    encode_text_input,
    project_case_input,
    project_editor,
    project_import_mapping,
    project_schema,
    transform_import_mapping,
)
from deykit.application.definitions import DecisionService, DecisionView, Versioned
from deykit.application.projects import ProjectBackend
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.records import DecisionDraft, DecisionRecord, DecisionRevision
from deykit.domain.definitions import definition_hash

from ..dto.authoring import (
    CaseInputProjectionRequest,
    DecisionCreateRequest,
    DecisionDTO,
    DecisionETagRequest,
    DecisionPageDTO,
    DefinitionDiffDTO,
    DraftRequest,
    DraftTransformReviewDTO,
    EditorProjectionRequest,
    EditorTransformRequest,
    MappingProjectionRequest,
    MappingTransformRequest,
    RenameDecisionRequest,
    RestoreRevisionRequest,
    RevisionDTO,
    RevisionPageDTO,
    SaveRevisionRequest,
    SchemaProjectionRequest,
    SelectionDTO,
    SelectionRequest,
    TextInputRequest,
    ValidationDTO,
)
from ..dto.common import Success, Versioned as VersionedDTO, VersionRequest
from ..registry import ProjectRegistry
from ..query import boolean, decimal
from ..runtime import TrackedWorkers


def _service(source: ProjectBackend, dependencies: ApiDependencies) -> DecisionService:
    return DecisionService(source, dependencies.clock, dependencies.id_factory)


def _decision(value: DecisionView) -> DecisionDTO:
    return DecisionDTO(
        decision=VersionedDTO(record=value.decision.record, etag=value.decision.etag),
        draft=VersionedDTO(record=value.draft.record, etag=value.draft.etag),
    )


def _draft(value: Versioned[DecisionDraft]) -> VersionedDTO[DecisionDraft]:
    return VersionedDTO(record=value.record, etag=value.etag)


def _record(value: Versioned[DecisionRecord]) -> VersionedDTO[DecisionRecord]:
    return VersionedDTO(record=value.record, etag=value.etag)


def _revision(value: Versioned[DecisionRevision]) -> RevisionDTO:
    return RevisionDTO(revision=VersionedDTO(record=value.record, etag=value.etag))


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def service(registration_id: str) -> DecisionService:
        return _service(registry.require(registration_id).source, dependencies)

    @router.get(
        "/projects/{registration_id}/decisions",
        response_model=Success[DecisionPageDTO],
        operation_id="listDecisions",
    )
    async def list_decisions(
        registration_id: str,
        include_archived: str = "false",
        cursor: str | None = None,
        limit: str = "50",
    ) -> Success[DecisionPageDTO]:
        page = await workers.run_sync(
            service(registration_id).list,
            include_archived=boolean(include_archived, reason="invalid_include_archived"),
            cursor=cursor,
            limit=decimal(limit, reason="invalid_page_limit", minimum=1, maximum=500),
        )
        return Success(
            data=DecisionPageDTO(
                items=tuple(_decision(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
            )
        )

    @router.post(
        "/projects/{registration_id}/decisions",
        response_model=Success[DecisionDTO],
        operation_id="createDecision",
    )
    async def create_decision(
        registration_id: str, body: DecisionCreateRequest, response: Response
    ) -> Success[DecisionDTO]:
        created = await workers.run_sync(
            service(registration_id).create,
            body.decision_id,
            body.name,
            body.editor_source,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{created.decision.etag}"'
        return Success(data=_decision(created))

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}",
        response_model=Success[DecisionDTO],
        operation_id="readDecision",
    )
    async def read_decision(
        registration_id: str, decision_id: str, response: Response
    ) -> Success[DecisionDTO]:
        value = await workers.run_sync(service(registration_id).read, decision_id)
        response.headers["ETag"] = f'"{value.decision.etag}"'
        return Success(data=_decision(value))

    @router.put(
        "/projects/{registration_id}/decisions/{decision_id}/draft",
        response_model=Success[VersionedDTO[DecisionDraft]],
        operation_id="updateDecisionDraft",
    )
    async def update_draft(
        registration_id: str, decision_id: str, body: DraftRequest, response: Response
    ) -> Success[VersionedDTO[DecisionDraft]]:
        value = await workers.run_sync(
            service(registration_id).update_draft,
            decision_id,
            body.editor_source,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_draft(value))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/validate",
        response_model=Success[ValidationDTO],
        operation_id="validateDecision",
    )
    async def validate_decision(
        registration_id: str, decision_id: str, body: VersionRequest
    ) -> Success[ValidationDTO]:
        del body
        definition = await workers.run_sync(service(registration_id).validate, decision_id)
        return Success(data=ValidationDTO(definition=definition, content_hash=definition_hash(definition)))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/selection-preview",
        response_model=Success[SelectionDTO],
        operation_id="previewCaseSelection",
    )
    async def selection_preview(
        registration_id: str, decision_id: str, body: SelectionRequest
    ) -> Success[SelectionDTO]:
        selected = await workers.run_sync(
            service(registration_id).select_case, decision_id, body.input_source
        )
        return Success(
            data=SelectionDTO(
                input_source=selected.source,
                content_hash=bytes_hash(selected.source.encode("utf-8")),
            )
        )

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/revisions",
        response_model=Success[RevisionDTO],
        operation_id="saveDecisionRevision",
    )
    async def save_revision(
        registration_id: str, decision_id: str, body: SaveRevisionRequest, response: Response
    ) -> Success[RevisionDTO]:
        value = await workers.run_sync(
            service(registration_id).save,
            decision_id,
            expected_draft_etag=body.expected_draft_etag,
            expected_decision_etag=body.expected_decision_etag,
            operation_id=body.operation_id,
            note=body.note,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_revision(value))

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/revisions",
        response_model=Success[RevisionPageDTO],
        operation_id="listDecisionRevisions",
    )
    async def revision_history(
        registration_id: str,
        decision_id: str,
        cursor: str | None = None,
        limit: str = "50",
    ) -> Success[RevisionPageDTO]:
        page = await workers.run_sync(
            service(registration_id).history,
            decision_id,
            cursor=cursor,
            limit=decimal(limit, reason="invalid_page_limit", minimum=1, maximum=500),
        )
        return Success(
            data=RevisionPageDTO(
                items=tuple(_revision(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/latest-revision",
        response_model=Success[RevisionDTO],
        operation_id="latestDecisionRevision",
    )
    async def latest_revision(registration_id: str, decision_id: str) -> Success[RevisionDTO]:
        latest = await workers.run_sync(service(registration_id).latest_saved_revision, decision_id)
        return Success(data=_revision(latest.revision))

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/revisions/{revision_id}",
        response_model=Success[RevisionDTO],
        operation_id="readDecisionRevision",
    )
    async def read_revision(
        registration_id: str, decision_id: str, revision_id: str, response: Response
    ) -> Success[RevisionDTO]:
        value = await workers.run_sync(service(registration_id).revision, decision_id, revision_id)
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_revision(value))

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/diff",
        response_model=Success[DefinitionDiffDTO],
        operation_id="diffDecisionRevisions",
    )
    async def diff_decisions(
        registration_id: str, decision_id: str, before: str, after: str
    ) -> Success[DefinitionDiffDTO]:
        value = await workers.run_sync(
            service(registration_id).diff, decision_id, before, after
        )
        return Success(data=DefinitionDiffDTO(**value.__dict__))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/rename",
        response_model=Success[VersionedDTO[DecisionRecord]],
        operation_id="renameDecision",
    )
    async def rename_decision(
        registration_id: str, decision_id: str, body: RenameDecisionRequest, response: Response
    ) -> Success[VersionedDTO[DecisionRecord]]:
        value = await workers.run_sync(
            service(registration_id).rename,
            decision_id,
            body.name,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_record(value))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/archive",
        response_model=Success[VersionedDTO[DecisionRecord]],
        operation_id="archiveDecision",
    )
    async def archive_decision(
        registration_id: str,
        decision_id: str,
        body: DecisionETagRequest,
        response: Response,
    ) -> Success[VersionedDTO[DecisionRecord]]:
        value = await workers.run_sync(
            service(registration_id).archive,
            decision_id,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_record(value))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/restore",
        response_model=Success[VersionedDTO[DecisionRecord]],
        operation_id="restoreDecision",
    )
    async def restore_decision(
        registration_id: str,
        decision_id: str,
        body: DecisionETagRequest,
        response: Response,
    ) -> Success[VersionedDTO[DecisionRecord]]:
        value = await workers.run_sync(
            service(registration_id).restore,
            decision_id,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_record(value))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/restore-revision",
        response_model=Success[VersionedDTO[DecisionDraft]],
        operation_id="restoreDecisionRevisionToDraft",
    )
    async def restore_revision(
        registration_id: str,
        decision_id: str,
        body: RestoreRevisionRequest,
        response: Response,
    ) -> Success[VersionedDTO[DecisionDraft]]:
        value = await workers.run_sync(
            service(registration_id).restore_revision_to_draft,
            decision_id,
            body.revision_id,
            expected_draft_etag=body.expected_draft_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_draft(value))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/editor-projection",
        response_model=Success[EditorProjectionV1],
        operation_id="projectDecisionEditor",
    )
    async def editor_projection(
        registration_id: str, decision_id: str, body: EditorProjectionRequest
    ) -> Success[EditorProjectionV1]:
        await workers.run_sync(service(registration_id).read, decision_id)
        return Success(data=await workers.run_sync(project_editor, body.editor_source))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/editor-transform",
        response_model=Success[DraftTransformReviewDTO],
        operation_id="transformDecisionEditor",
    )
    async def editor_transform(
        registration_id: str, decision_id: str, body: EditorTransformRequest
    ) -> Success[DraftTransformReviewDTO]:
        reviewed = await workers.run_sync(
            service(registration_id).review_draft_transform,
            decision_id,
            body.editor_source,
            body.edit,
            expected_draft_etag=body.expected_draft_etag,
        )
        return Success(
            data=DraftTransformReviewDTO(
                transform=reviewed.transform,
                incompatible_references=reviewed.incompatible_references,
            )
        )

    @router.post(
        "/projects/{registration_id}/authoring/schema-projection",
        response_model=Success[SchemaProjectionV1],
        operation_id="projectInputSchema",
    )
    async def schema_projection(
        registration_id: str, body: SchemaProjectionRequest
    ) -> Success[SchemaProjectionV1]:
        registry.require(registration_id)
        return Success(data=await workers.run_sync(project_schema, body.schema_source))

    @router.post(
        "/projects/{registration_id}/authoring/case-input-projection",
        response_model=Success[CaseInputProjectionV1],
        operation_id="projectCaseInput",
    )
    async def case_input_projection(
        registration_id: str, body: CaseInputProjectionRequest
    ) -> Success[CaseInputProjectionV1]:
        registry.require(registration_id)
        return Success(
            data=await workers.run_sync(project_case_input, body.input_kind, body.input_source)
        )

    @router.post(
        "/projects/{registration_id}/authoring/text-input",
        response_model=Success[EncodedInputV1],
        operation_id="encodeTextInput",
    )
    async def text_input(
        registration_id: str, body: TextInputRequest
    ) -> Success[EncodedInputV1]:
        registry.require(registration_id)
        return Success(data=await workers.run_sync(encode_text_input, body.text_value))

    @router.post(
        "/projects/{registration_id}/authoring/mapping-projection",
        response_model=Success[MappingProjectionV1],
        operation_id="projectImportMapping",
    )
    async def mapping_projection(
        registration_id: str, body: MappingProjectionRequest
    ) -> Success[MappingProjectionV1]:
        registry.require(registration_id)
        return Success(data=await workers.run_sync(project_import_mapping, body.mapping_source))

    @router.post(
        "/projects/{registration_id}/authoring/mapping-transform",
        response_model=Success[MappingTransformV1],
        operation_id="transformImportMapping",
    )
    async def mapping_transform(
        registration_id: str, body: MappingTransformRequest
    ) -> Success[MappingTransformV1]:
        registry.require(registration_id)
        return Success(
            data=await workers.run_sync(transform_import_mapping, body.mapping_source, body.edit)
        )
