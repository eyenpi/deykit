"""Dataset, case, import, and split routes over the retained project source."""

import re
from typing import Literal

from fastapi import APIRouter, Response

from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.dto.common import Success
from deykit.api.dto.data import (
    CaseChangeRequest,
    CaseDTO,
    CaseEditRequest,
    CaseInputRequest,
    CaseMutationDTO,
    CasePageDTO,
    CaseReadDTO,
    DatasetChangeRequest,
    DatasetDTO,
    DatasetCreateRequest,
    DatasetPageDTO,
    DatasetPatchRequest,
    ImportCommitDTO,
    ImportCommitRequest,
    ImportPreviewDTO,
    ImportPreviewRecordDTO,
    ImportPreviewRequest,
    ImportRowDTO,
    ServiceErrorDTO,
    SplitCommitDTO,
    SplitCommitRequest,
    SplitPreviewDTO,
    SplitPreviewRecordDTO,
)
from deykit.api.query import boolean, decimal
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.application.dataset_support import CaseView, DatasetView
from deykit.application.datasets import CaseInput, CasePage, DatasetService
from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportPreview, ImportRow, ImportService
from deykit.application.preview_documents import (
    decode_import_preview,
    decode_split_preview,
    encode_import_preview,
    encode_split_preview,
)
from deykit.application.splits import SplitPreview, SplitService
from deykit.contracts.errors import ServiceError


_SIGNED = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")


def _invalid(reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason=reason))


def _dataset(value: DatasetView) -> DatasetDTO:
    return DatasetDTO(record=value.record, etag=value.etag)


def _case(value: CaseView) -> CaseDTO:
    return CaseDTO(record=value.record, etag=value.etag)


def _page_limit(value: str | None) -> int:
    return 50 if value is None else decimal(
        value, reason="invalid_integer_query", minimum=1, maximum=500
    )


def _case_page_snapshot(
    source: ApiProjectSource,
    service: DatasetService,
    dataset_id: str,
    *,
    cursor: str | None,
    limit: int,
    tag: str | None,
    group_id: str | None,
    split: Literal["development", "calibration", "test"] | None,
) -> tuple[CasePage, DatasetView]:
    with source.consistent_read():
        return (
            service.list_cases(
                dataset_id,
                cursor=cursor,
                limit=limit,
                tag=tag,
                group_id=group_id,
                split=split,
            ),
            service.read(dataset_id),
        )


def _case_snapshot(
    source: ApiProjectSource,
    service: DatasetService,
    dataset_id: str,
    case_id: str,
) -> tuple[CaseView, DatasetView]:
    with source.consistent_read():
        return service.case(dataset_id, case_id), service.read(dataset_id)


def _case_input(body: CaseInputRequest) -> CaseInput:
    return CaseInput(
        input_kind=body.input_kind,
        input_source=body.input_source,
        tags=body.tags,
        split=body.split,
        group_id=body.group_id,
        derived_from=body.derived_from,
        metadata_source=body.metadata_source,
    )


def _dataset_patch_values(body: DatasetPatchRequest) -> dict[str, str]:
    fields = body.model_fields_set - {"schema_version", "operation_id", "expected_etag"}
    if not fields:
        raise _invalid("invalid_dataset_patch")
    values: dict[str, str] = {}
    if "name" in fields:
        if body.name is None:
            raise _invalid("invalid_dataset_patch")
        values["name"] = body.name
    if "metadata_source" in fields:
        if body.metadata_source is None:
            raise _invalid("invalid_dataset_patch")
        values["metadata_source"] = body.metadata_source
    return values


def _import_row(row: ImportRow) -> ImportRowDTO:
    return ImportRowDTO(
        row=str(row.row),
        source_line=str(row.source_line),
        case=row.case,
        acceptable_option_ids=row.acceptable_option_ids,
        errors=tuple(
            ServiceErrorDTO(
                code=error.code,
                message=error.message,
                resource_id=error.resource_id,
                row=str(error.row) if error.row is not None else None,
                reason=error.reason,
            )
            for error in row.errors
        ),
        duplicate_input_ids=row.duplicate_input_ids,
    )


def _import_preview(preview: ImportPreview) -> ImportPreviewDTO:
    return ImportPreviewDTO(
        preview=ImportPreviewRecordDTO(
            dataset_id=preview.dataset_id,
            dataset_etag=preview.dataset_etag,
            source_text=preview.source_text,
            source_hash=preview.source_hash,
            format=preview.format,
            mapping=preview.mapping,
            mapping_hash=preview.mapping_hash,
            decision_id=preview.decision_id,
            decision_selector=preview.decision_selector,
            context_hash=preview.context_hash,
            question_id=preview.question_id,
            rows=tuple(_import_row(row) for row in preview.rows),
            preview_hash=preview.preview_hash,
        ),
        would_import=str(len(preview.valid_rows)),
        preview_document_source=encode_import_preview(preview),
    )


def _split_preview(preview: SplitPreview) -> SplitPreviewDTO:
    return SplitPreviewDTO(
        preview=SplitPreviewRecordDTO(
            dataset_id=preview.dataset_id,
            dataset_etag=preview.dataset_etag,
            input_identity=preview.input_identity,
            algorithm=preview.algorithm,
            seed=str(preview.seed) if preview.seed is not None else None,
            ratios_source=preview.ratios_source,
            assignments=preview.assignments,
            groups=preview.groups,
            counts=tuple((name, str(count)) for name, count in preview.counts),
        ),
        preview_document_source=encode_split_preview(preview),
    )


def _seed(source: str) -> int:
    if len(source) > 20 or _SIGNED.fullmatch(source) is None:
        raise _invalid("invalid_split_seed")
    value = int(source)
    if not -(2**63) <= value <= 2**63 - 1:
        raise _invalid("invalid_split_seed")
    return value


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def source_for(registration_id: str) -> ApiProjectSource:
        return registry.require(registration_id).source

    def datasets(source: ApiProjectSource) -> DatasetService:
        return DatasetService(source, dependencies.clock, dependencies.id_factory)

    @router.get("/projects/{registration_id}/datasets", response_model=Success[DatasetPageDTO])
    async def list_datasets(
        registration_id: str,
        include_archived: str | None = None,
        cursor: str | None = None,
        limit: str | None = None,
    ) -> Success[DatasetPageDTO]:
        service = datasets(source_for(registration_id))
        page = await workers.run_sync(
            service.list,
            include_archived=(
                boolean(include_archived, reason="invalid_boolean_query")
                if include_archived is not None
                else False
            ),
            cursor=cursor,
            limit=_page_limit(limit),
        )
        return Success(
            data=DatasetPageDTO(
                items=tuple(_dataset(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
            )
        )

    @router.post(
        "/projects/{registration_id}/datasets",
        response_model=Success[DatasetDTO],
        operation_id="createDataset",
    )
    async def create_dataset(
        registration_id: str, body: DatasetCreateRequest, response: Response
    ) -> Success[DatasetDTO]:
        service = datasets(source_for(registration_id))
        value = await workers.run_sync(
            service.create,
            body.name,
            dataset_id=body.dataset_id,
            metadata_source=body.metadata_source,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_dataset(value))

    @router.get(
        "/projects/{registration_id}/datasets/{dataset_id}",
        response_model=Success[DatasetDTO],
    )
    async def read_dataset(
        registration_id: str, dataset_id: str, response: Response
    ) -> Success[DatasetDTO]:
        value = await workers.run_sync(datasets(source_for(registration_id)).read, dataset_id)
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_dataset(value))

    @router.patch(
        "/projects/{registration_id}/datasets/{dataset_id}",
        response_model=Success[DatasetDTO],
    )
    async def patch_dataset(
        registration_id: str,
        dataset_id: str,
        body: DatasetPatchRequest,
        response: Response,
    ) -> Success[DatasetDTO]:
        value = await workers.run_sync(
            datasets(source_for(registration_id)).update,
            dataset_id,
            **_dataset_patch_values(body),
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_dataset(value))

    async def change_dataset(
        registration_id: str,
        dataset_id: str,
        body: DatasetChangeRequest,
        response: Response,
        action: Literal["archive", "restore"],
    ) -> Success[DatasetDTO]:
        service = datasets(source_for(registration_id))
        operation = service.archive if action == "archive" else service.restore
        value = await workers.run_sync(
            operation,
            dataset_id,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.etag}"'
        return Success(data=_dataset(value))

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/archive",
        response_model=Success[DatasetDTO],
    )
    async def archive_dataset(
        registration_id: str,
        dataset_id: str,
        body: DatasetChangeRequest,
        response: Response,
    ) -> Success[DatasetDTO]:
        return await change_dataset(registration_id, dataset_id, body, response, "archive")

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/restore",
        response_model=Success[DatasetDTO],
    )
    async def restore_dataset(
        registration_id: str,
        dataset_id: str,
        body: DatasetChangeRequest,
        response: Response,
    ) -> Success[DatasetDTO]:
        return await change_dataset(registration_id, dataset_id, body, response, "restore")

    @router.get(
        "/projects/{registration_id}/datasets/{dataset_id}/cases",
        response_model=Success[CasePageDTO],
    )
    async def list_cases(
        registration_id: str,
        dataset_id: str,
        cursor: str | None = None,
        limit: str | None = None,
        tag: str | None = None,
        group_id: str | None = None,
        split: Literal["development", "calibration", "test"] | None = None,
    ) -> Success[CasePageDTO]:
        source = source_for(registration_id)
        service = datasets(source)
        page, dataset = await workers.run_sync(
            _case_page_snapshot,
            source,
            service,
            dataset_id,
            cursor=cursor,
            limit=_page_limit(limit),
            tag=tag,
            group_id=group_id,
            split=split,
        )
        return Success(
            data=CasePageDTO(
                items=tuple(_case(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
                dataset_etag=dataset.etag,
            )
        )

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/cases",
        response_model=Success[CaseMutationDTO],
    )
    async def add_case(
        registration_id: str, dataset_id: str, body: CaseInputRequest
    ) -> Success[CaseMutationDTO]:
        result = await workers.run_sync(
            datasets(source_for(registration_id)).add_case,
            dataset_id,
            _case_input(body),
            expected_dataset_etag=body.expected_dataset_etag,
            operation_id=body.operation_id,
            case_id=body.case_id,
        )
        return Success(
            data=CaseMutationDTO(
                dataset=_dataset(result.dataset),
                case=_case(result.case) if result.case is not None else None,
                cleared_label_ids=result.cleared_label_ids,
                replayed=result.replayed,
            )
        )

    @router.get(
        "/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}",
        response_model=Success[CaseReadDTO],
    )
    async def read_case(
        registration_id: str, dataset_id: str, case_id: str
    ) -> Success[CaseReadDTO]:
        source = source_for(registration_id)
        service = datasets(source)
        case, dataset = await workers.run_sync(
            _case_snapshot, source, service, dataset_id, case_id
        )
        return Success(data=CaseReadDTO(case=_case(case), dataset_etag=dataset.etag))

    @router.put(
        "/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}",
        response_model=Success[CaseMutationDTO],
    )
    async def edit_case(
        registration_id: str,
        dataset_id: str,
        case_id: str,
        body: CaseEditRequest,
    ) -> Success[CaseMutationDTO]:
        service = datasets(source_for(registration_id))

        result = await workers.run_sync(
            service.edit_case,
            dataset_id,
            case_id,
            CaseInput(
                input_kind=body.input_kind,
                input_source=body.input_source,
                tags=body.tags,
                split=body.split,
                group_id=body.group_id,
                derived_from=body.derived_from,
                metadata_source=body.metadata_source,
            ),
            expected_dataset_etag=body.expected_dataset_etag,
            expected_case_etag=body.expected_case_etag,
            operation_id=body.operation_id,
        )
        return Success(
            data=CaseMutationDTO(
                dataset=_dataset(result.dataset),
                case=_case(result.case) if result.case is not None else None,
                cleared_label_ids=result.cleared_label_ids,
                replayed=result.replayed,
            )
        )

    @router.delete(
        "/projects/{registration_id}/datasets/{dataset_id}/cases/{case_id}",
        response_model=Success[CaseMutationDTO],
    )
    async def delete_case(
        registration_id: str,
        dataset_id: str,
        case_id: str,
        body: CaseChangeRequest,
    ) -> Success[CaseMutationDTO]:
        result = await workers.run_sync(
            datasets(source_for(registration_id)).remove_case,
            dataset_id,
            case_id,
            expected_dataset_etag=body.expected_dataset_etag,
            expected_case_etag=body.expected_case_etag,
            operation_id=body.operation_id,
        )
        return Success(
            data=CaseMutationDTO(
                dataset=_dataset(result.dataset),
                case=_case(result.case) if result.case is not None else None,
                cleared_label_ids=result.cleared_label_ids,
                replayed=result.replayed,
            )
        )

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/imports/preview",
        response_model=Success[ImportPreviewDTO],
    )
    async def preview_import(
        registration_id: str, dataset_id: str, body: ImportPreviewRequest
    ) -> Success[ImportPreviewDTO]:
        service = ImportService(
            source_for(registration_id), dependencies.clock, dependencies.id_factory
        )
        mapping = await workers.run_sync(ImportService.parse_mapping, body.mapping_source)
        preview = await workers.run_sync(
            service.preview,
            dataset_id,
            body.source_text,
            format=body.format,
            mapping=mapping,
            decision_id=body.decision_id,
            decision_selector=body.decision_selector,
        )
        return Success(data=_import_preview(preview))

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/imports/commit",
        response_model=Success[ImportCommitDTO],
    )
    async def commit_import(
        registration_id: str, dataset_id: str, body: ImportCommitRequest
    ) -> Success[ImportCommitDTO]:
        service = ImportService(
            source_for(registration_id), dependencies.clock, dependencies.id_factory
        )
        preview = await workers.run_sync(
            decode_import_preview, body.preview_document_source, dataset_id
        )
        result = await workers.run_sync(
            service.commit,
            preview,
            operation_id=body.operation_id,
            skip_invalid=body.skip_invalid,
        )
        return Success(
            data=ImportCommitDTO(
                dataset=_dataset(result.dataset),
                imported_case_ids=result.imported_case_ids,
                exclusions=tuple(_import_row(row) for row in result.exclusions),
                duplicate_rows=tuple(_import_row(row) for row in result.duplicate_rows),
                replayed=result.replayed,
            )
        )

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/splits/preview",
        response_model=Success[SplitPreviewDTO],
    )
    async def preview_split(
        registration_id: str, dataset_id: str, body: SplitPreviewRequest
    ) -> Success[SplitPreviewDTO]:
        service = SplitService(
            source_for(registration_id), dependencies.clock, dependencies.id_factory
        )
        seed = _seed(body.seed)
        preview = await workers.run_sync(
            service.preview,
            dataset_id,
            seed=seed,
            ratios_source=body.ratios_source,
            assignments=body.assignments,
        )
        return Success(data=_split_preview(preview))

    @router.post(
        "/projects/{registration_id}/datasets/{dataset_id}/splits/commit",
        response_model=Success[SplitCommitDTO],
    )
    async def commit_split(
        registration_id: str, dataset_id: str, body: SplitCommitRequest
    ) -> Success[SplitCommitDTO]:
        service = SplitService(
            source_for(registration_id), dependencies.clock, dependencies.id_factory
        )
        preview = await workers.run_sync(
            decode_split_preview, body.preview_document_source, dataset_id
        )
        result = await workers.run_sync(
            service.commit, preview, operation_id=body.operation_id
        )
        return Success(
            data=SplitCommitDTO(
                dataset=_dataset(result.dataset),
                snapshot=result.snapshot,
                replayed=result.replayed,
            )
        )
