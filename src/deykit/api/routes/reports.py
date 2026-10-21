"""Saved report metadata and protected exact-byte downloads."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from starlette.responses import Response

from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Success
from deykit.api.dto.reports import CreateReportRequest, ReportDTO, ReportPageDTO
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.application.errors import ServiceFailure
from deykit.application.reports import ReportService
from deykit.contracts.errors import ServiceError
from deykit.contracts.report_json import REPORT_ARTIFACT_MAX_BYTES
from deykit.reports.models import ReportMetadata

_DOWNLOAD_FORMATS = {
    "json": {"contentType": "application/octet-stream", "extension": "json"},
    "markdown": {"contentType": "text/plain; charset=utf-8", "extension": "md"},
    "csv": {"contentType": "text/csv; charset=utf-8", "extension": "csv"},
}
_DOWNLOAD_POLICY = {
    "formatParameter": "format",
    "reportIdParameter": "report_id",
    "maxBytes": REPORT_ARTIFACT_MAX_BYTES,
    "formats": _DOWNLOAD_FORMATS,
}


def _report(value: ReportMetadata) -> ReportDTO:
    return ReportDTO.model_validate(value.model_dump(mode="python"))


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def service(registration_id: str) -> ReportService:
        return ReportService(
            registry.require(registration_id).source,
            dependencies.clock,
            dependencies.id_factory,
        )

    @router.post(
        "/projects/{registration_id}/reports",
        response_model=Success[ReportDTO],
        operation_id="createReport",
    )
    async def create_report(registration_id: str, body: CreateReportRequest) -> Success[ReportDTO]:
        value = await workers.run_sync(
            service(registration_id).create,
            body.to_application(),
            operation_id=body.operation_id,
        )
        report = await workers.run_sync(service(registration_id).metadata, value.record.id)
        return Success(data=_report(report))

    @router.get(
        "/projects/{registration_id}/reports",
        response_model=Success[ReportPageDTO],
        operation_id="listReports",
    )
    async def list_reports(
        registration_id: str,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Success[ReportPageDTO]:
        value = await workers.run_sync(service(registration_id).list, cursor=cursor, limit=limit)
        return Success(
            data=ReportPageDTO(
                items=tuple(_report(item) for item in value.items),
                total=str(value.total),
                next_cursor=value.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/reports/{report_id}",
        response_model=Success[ReportDTO],
        operation_id="readReport",
    )
    async def read_report(registration_id: str, report_id: str) -> Success[ReportDTO]:
        value = await workers.run_sync(service(registration_id).metadata, report_id)
        return Success(data=_report(value))

    @router.get(
        "/projects/{registration_id}/reports/{report_id}/download",
        operation_id="downloadReport",
        response_class=Response,
        response_model=None,
        openapi_extra={"x-deykit-report-download-v1": _DOWNLOAD_POLICY},
        responses={
            200: {
                "description": "Saved report bytes",
                "headers": {
                    "Content-Disposition": {
                        "description": "Fixed attachment name report-{report_id}.{json|md}",
                        "schema": {"type": "string"},
                    },
                    "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
                    "X-Content-Type-Options": {"schema": {"type": "string", "const": "nosniff"}},
                },
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                    "text/plain; charset=utf-8": {"schema": {"type": "string", "format": "binary"}},
                    "text/csv; charset=utf-8": {"schema": {"type": "string", "format": "binary"}},
                },
            }
        },
    )
    async def download_report(
        registration_id: str,
        report_id: str,
        format: Literal["json", "markdown", "csv"],
    ) -> Response:
        # Resolve registration before translating report errors, so admission failures never
        # disclose a guessed report identity.
        active = service(registration_id)
        try:
            artifact = await workers.run_sync(active.render, report_id, format=format)
        except ServiceFailure as error:
            if error.error.resource_id is not None:
                raise
            retained = ServiceError(
                code=error.error.code,
                resource_id=report_id,
                row=error.error.row,
                reason=error.error.reason,
            )
            raise ServiceFailure(retained, selection=error.selection) from None
        policy = _DOWNLOAD_FORMATS[format]
        extension = policy["extension"]
        media = policy["contentType"]
        return Response(
            content=artifact.body,
            status_code=200,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="report-{report_id}.{extension}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
