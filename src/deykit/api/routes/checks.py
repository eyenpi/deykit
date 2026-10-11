"""Frozen regression-check groups over the shared durable group service."""

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
    StartCheckRequest,
)
from deykit.api.dto.groups import (
    CheckSnapshotCaseDTO,
    CheckSnapshotDetailDTO,
    CheckViewDTO,
    FrozenMemberContextDTO,
    SnapshotMetadataDTO,
    SnapshotResultDTO,
)
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.api.supervisor import ExecutionSupervisor
from deykit.application.checks import CheckService
from deykit.application.evaluations import FrozenEvaluation
from deykit.contracts.execution_groups import CheckSnapshot
from deykit.domain.definitions import definition_hash

from .execution import execution_service
from .group_views import group_progress, group_resume_preview


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
    supervisor: ExecutionSupervisor,
) -> None:
    def service(registration_id: str) -> CheckService:
        return CheckService(execution_service(registration_id, dependencies, registry))

    def snapshot_metadata(value: CheckSnapshot) -> SnapshotMetadataDTO:
        return SnapshotMetadataDTO(
            id=value.id,
            sequence=str(value.sequence),
            group_id=value.group_id,
            segment_id=value.segment_id,
            content_hash=value.content_hash,
            created_at=value.created_at,
            results=tuple(
                SnapshotResultDTO(run_id=item.run_id, result_snapshot_id=item.result_snapshot_id)
                for item in value.results
            ),
        )

    def member_context(value: FrozenEvaluation) -> FrozenMemberContextDTO:
        return FrozenMemberContextDTO(
            run_id=value.manifest.id,
            result_snapshot_id=value.results.id,
            result_content_hash=value.results.content_hash,
            through_event_sequence=str(value.results.through_event_sequence),
            label_snapshot_id=value.labels.id,
            label_content_hash=value.labels.content_hash,
            decision_id=cast(str, value.manifest.decision_id),
            dataset_id=cast(str, value.manifest.dataset_id),
            decision_revision_id=value.revision.id,
            decision_definition_hash=definition_hash(value.revision.definition),
            dataset_snapshot_id=value.dataset.id,
            dataset_content_hash=value.dataset.content_hash,
        )

    @router.get(
        "/projects/{registration_id}/checks/{group_id}/snapshots",
        response_model=Success[tuple[SnapshotMetadataDTO, ...]],
        operation_id="listCheckSnapshots",
    )
    async def list_check_snapshots(
        registration_id: str, group_id: str
    ) -> Success[tuple[SnapshotMetadataDTO, ...]]:
        values = await workers.run_sync(service(registration_id).list_snapshots, group_id)
        return Success(data=tuple(snapshot_metadata(item) for item in values))

    @router.get(
        "/projects/{registration_id}/checks/{group_id}/snapshots/{snapshot_id}",
        response_model=Success[CheckSnapshotDetailDTO],
        operation_id="readCheckSnapshot",
    )
    async def read_check_snapshot(
        registration_id: str, group_id: str, snapshot_id: str
    ) -> Success[CheckSnapshotDetailDTO]:
        value = await workers.run_sync(service(registration_id).read_snapshot, group_id, snapshot_id)
        return Success(
            data=CheckSnapshotDetailDTO(
                snapshot=snapshot_metadata(value.snapshot),
                members=tuple(member_context(item) for item in value.members),
                cases=tuple(CheckSnapshotCaseDTO(**item.__dict__) for item in value.cases),
                expectation_failures=str(value.expectation_failures),
                baseline_unavailable=value.baseline_unavailable,
            )
        )

    @router.post(
        "/projects/{registration_id}/checks",
        response_model=Success[GroupAcceptedDTO],
        status_code=202,
        operation_id="startRegressionCheck",
        responses={202: {"headers": {"Location": {"schema": {"type": "string"}}}}},
    )
    async def start_check(
        registration_id: str, body: StartCheckRequest, response: Response
    ) -> Success[GroupAcceptedDTO]:
        registration = registry.require(registration_id)
        accepted = await supervisor.start_group(
            registration,
            service(registration_id),
            "regression_check",
            body.request.to_application(),
            operation_id=body.operation_id,
            expected_review_context_hash=body.expected_review_context_hash,
        )
        response.headers["Location"] = accepted.progress_path
        return Success(data=GroupAcceptedDTO(**accepted.__dict__))

    @router.get(
        "/projects/{registration_id}/checks/{group_id}",
        response_model=Success[CheckViewDTO],
        operation_id="readCheck",
    )
    async def read_check(registration_id: str, group_id: str) -> Success[CheckViewDTO]:
        value = await workers.run_sync(service(registration_id).read, group_id)
        return Success(
            data=CheckViewDTO(
                group=group_progress(value.group),
                cases=tuple(item.__dict__ for item in value.cases),
                expectation_failures=str(value.expectation_failures),
                baseline_unavailable=value.baseline_unavailable,
                exit_code=value.exit_code,
            )
        )

    @router.post(
        "/projects/{registration_id}/checks/{group_id}/cancel",
        response_model=Success[GroupProgressDTO],
        operation_id="cancelCheck",
    )
    async def cancel_check(
        registration_id: str, group_id: str, body: GroupCancelRequest
    ) -> Success[GroupProgressDTO]:
        value = await workers.run_sync(
            service(registration_id).cancel, group_id, operation_id=body.operation_id
        )
        return Success(data=group_progress(value))

    @router.post(
        "/projects/{registration_id}/checks/{group_id}/resume-preview",
        response_model=Success[GroupResumePreviewDTO],
        operation_id="previewCheckResume",
    )
    async def preview_check_resume(
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
        "/projects/{registration_id}/checks/{group_id}/resume",
        response_model=Success[GroupAcceptedDTO],
        status_code=202,
        operation_id="resumeCheck",
        responses={202: {"headers": {"Location": {"schema": {"type": "string"}}}}},
    )
    async def resume_check(
        registration_id: str, group_id: str, body: GroupResumeRequest, response: Response
    ) -> Success[GroupAcceptedDTO]:
        registration = registry.require(registration_id)
        accepted = await supervisor.resume_group(
            registration,
            service(registration_id),
            "regression_check",
            group_id,
            operation_id=body.operation_id,
            retry_unknown=body.retry_unknown,
        )
        response.headers["Location"] = accepted.progress_path
        return Success(data=GroupAcceptedDTO(**accepted.__dict__))
