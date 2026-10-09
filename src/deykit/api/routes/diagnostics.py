"""Choice-order diagnostics over the shared durable group service."""

from typing import Literal, cast

from fastapi import APIRouter, Response

from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Success, VersionRequest
from deykit.api.dto.execution import (
    GroupAcceptedDTO,
    GroupCancelRequest,
    GroupProgressDTO,
    GroupResumePreviewDTO,
    GroupResumeRequest,
    StartChoiceOrderRequest,
)
from deykit.api.dto.groups import DiagnosticViewDTO
from deykit.api.projections import exact_display_tree
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.api.supervisor import ExecutionSupervisor
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService

from .execution import execution_service
from .group_views import group_progress, group_resume_preview


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
    supervisor: ExecutionSupervisor,
) -> None:
    def service(registration_id: str) -> DiagnosticService:
        return DiagnosticService(execution_service(registration_id, dependencies, registry))

    @router.post(
        "/projects/{registration_id}/diagnostics/choice-order",
        response_model=Success[GroupAcceptedDTO],
        status_code=202,
        operation_id="startChoiceOrder",
        responses={202: {"headers": {"Location": {"schema": {"type": "string"}}}}},
    )
    async def start_choice_order(
        registration_id: str, body: StartChoiceOrderRequest, response: Response
    ) -> Success[GroupAcceptedDTO]:
        registration = registry.require(registration_id)
        request = ChoiceOrderRequest(
            run=body.request.run.to_application(),
            orders=body.request.orders,
            seed=int(body.request.seed),
        )
        accepted = await supervisor.start_group(
            registration,
            service(registration_id),
            "choice_order",
            request,
            operation_id=body.operation_id,
            expected_review_context_hash=body.expected_review_context_hash,
        )
        response.headers["Location"] = accepted.progress_path
        return Success(data=GroupAcceptedDTO(**accepted.__dict__))

    @router.get(
        "/projects/{registration_id}/diagnostics/{group_id}",
        response_model=Success[DiagnosticViewDTO],
        operation_id="readChoiceOrder",
    )
    async def read_choice_order(registration_id: str, group_id: str) -> Success[DiagnosticViewDTO]:
        value = await workers.run_sync(service(registration_id).read, group_id)
        return Success(
            data=DiagnosticViewDTO(
                group=group_progress(value.group),
                summary=cast(dict[str, object], exact_display_tree(value.summary.source()))
                if value.summary is not None
                else None,
                exit_code=value.exit_code,
            )
        )

    @router.post(
        "/projects/{registration_id}/diagnostics/{group_id}/cancel",
        response_model=Success[GroupProgressDTO],
        operation_id="cancelChoiceOrder",
    )
    async def cancel_choice_order(
        registration_id: str, group_id: str, body: GroupCancelRequest
    ) -> Success[GroupProgressDTO]:
        value = await workers.run_sync(
            service(registration_id).cancel, group_id, operation_id=body.operation_id
        )
        return Success(data=group_progress(value))

    @router.post(
        "/projects/{registration_id}/diagnostics/{group_id}/resume-preview",
        response_model=Success[GroupResumePreviewDTO],
        operation_id="previewChoiceOrderResume",
    )
    async def preview_choice_order_resume(
        registration_id: str,
        group_id: str,
        body: VersionRequest,
        retry_unknown: Literal["true", "false"] = "false",
    ) -> Success[GroupResumePreviewDTO]:
        del body
        value = await workers.run_sync(
            service(registration_id).preview_resume,
            group_id,
            retry_unknown=retry_unknown == "true",
        )
        return Success(data=group_resume_preview(value))

    @router.post(
        "/projects/{registration_id}/diagnostics/{group_id}/resume",
        response_model=Success[GroupAcceptedDTO],
        status_code=202,
        operation_id="resumeChoiceOrder",
        responses={202: {"headers": {"Location": {"schema": {"type": "string"}}}}},
    )
    async def resume_choice_order(
        registration_id: str, group_id: str, body: GroupResumeRequest, response: Response
    ) -> Success[GroupAcceptedDTO]:
        registration = registry.require(registration_id)
        accepted = await supervisor.resume_group(
            registration,
            service(registration_id),
            "choice_order",
            group_id,
            operation_id=body.operation_id,
            retry_unknown=body.retry_unknown,
        )
        response.headers["Location"] = accepted.progress_path
        return Success(data=GroupAcceptedDTO(**accepted.__dict__))
