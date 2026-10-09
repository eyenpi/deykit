"""Execution acknowledgement, polling, cancellation and recovery routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query, Response

from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Success, VersionRequest
from deykit.api.dto.execution import (
    RunAcceptedDTO,
    RunAttemptProgressDTO,
    RunCancelRequest,
    RunCaseProgressDTO,
    ExecutionSettingsViewDTO,
    RunPageDTO,
    RunProgressDTO,
    RunResumePreviewDTO,
    RunResumeRequest,
    RunSegmentProgressDTO,
    RunSourceReferencesDTO,
    StartRunRequest,
)
from deykit.api.projections import service_error
from deykit.api.query import decimal as query_decimal
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.api.supervisor import ExecutionSupervisor
from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.runner.views import ResumePreview, RunProgress


def execution_service(
    registration_id: str, dependencies: ApiDependencies, registry: ProjectRegistry
) -> ExecutionService:
    source = registry.require(registration_id).source
    return ExecutionService(
        source,
        source,
        dependencies.backends_factory(source, dependencies.clock),
        dependencies.clock,
        dependencies.id_factory,
    )


def evaluation_service(
    registration_id: str, registry: ProjectRegistry, dependencies: ApiDependencies
) -> EvaluationService:
    return EvaluationService(
        registry.require(registration_id).source, dependencies.clock, dependencies.id_factory
    )


def run_progress(value: RunProgress) -> RunProgressDTO:
    def decimal_text(number: float | None) -> str | None:
        if number is None:
            return None
        return format(Decimal(str(number)), "f")

    return RunProgressDTO(
        run_id=value.run_id,
        decision_id=value.decision_id,
        dataset_id=value.dataset_id,
        mode=value.mode,
        requested_model=value.requested_model,
        state=value.state,
        execution_active=value.execution_active,
        attempts_used=str(value.attempts_used),
        attempt_limit=str(value.attempt_limit),
        attempts_remaining=str(value.attempts_remaining),
        settings=ExecutionSettingsViewDTO.from_application(value.settings),
        sources=RunSourceReferencesDTO(
            decision_revision_id=value.sources.decision_revision_id,
            dataset_snapshot_id=value.sources.dataset_snapshot_id,
            label_snapshot_id=value.sources.label_snapshot_id,
            development_dataset_snapshot_id=value.sources.development_dataset_snapshot_id,
            development_label_snapshot_id=value.sources.development_label_snapshot_id,
            provider_profile_id=value.sources.provider_profile_id,
            fixture_set_id=value.sources.fixture_set_id,
            option_order=value.sources.option_order,
            adapter=value.sources.adapter,
            compiler_version=value.sources.compiler_version,
            compiler_id=value.sources.compiler_id,
            compiler_id_unavailable_reason=value.sources.compiler_id_unavailable_reason,
            evidence_mode=value.sources.evidence_mode,
        ),
        cases=tuple(
            RunCaseProgressDTO(
                case_id=item.case_id,
                status=item.status,
                attempt_id=item.attempt_id,
                error=service_error(item.error),
            )
            for item in value.cases
        ),
        attempts=tuple(
            RunAttemptProgressDTO(
                attempt_id=item.attempt_id,
                case_id=item.case_id,
                number=item.number,
                kind=item.kind,
                state=item.state,
                duration_seconds=decimal_text(item.duration_seconds),
            )
            for item in value.attempts
        ),
        segment_ids=value.segment_ids,
        segments=tuple(
            RunSegmentProgressDTO(
                segment_id=item.segment_id,
                started_at=item.started_at,
                deadline_at=item.deadline_at,
                ended_at=item.ended_at,
                retry_unknown=item.retry_unknown,
            )
            for item in value.segments
        ),
        result_snapshot_ids=value.result_snapshot_ids,
        latest_result_snapshot_id=value.latest_result_snapshot_id,
        replayed=value.replayed,
        execution_group_id=value.execution_group_id,
        group_attempts_remaining=(
            str(value.group_attempts_remaining)
            if value.group_attempts_remaining is not None
            else None
        ),
        reason=service_error(value.reason),
    )


def run_resume_preview(value: ResumePreview) -> RunResumePreviewDTO:
    return RunResumePreviewDTO(
        run=run_progress(value.run),
        planned_case_ids=value.planned_case_ids,
        retry_unknown=value.retry_unknown,
        proposed_attempt_limit=str(value.proposed_attempt_limit),
        dry_run=value.dry_run,
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
    supervisor: ExecutionSupervisor,
) -> None:
    @router.post(
        "/projects/{registration_id}/runs",
        response_model=Success[RunAcceptedDTO],
        status_code=202,
        operation_id="startRun",
        responses={202: {"headers": {"Location": {"schema": {"type": "string"}}}}},
    )
    async def start_run(
        registration_id: str, body: StartRunRequest, response: Response
    ) -> Success[RunAcceptedDTO]:
        registration = registry.require(registration_id)
        service = execution_service(registration_id, dependencies, registry)
        result = await supervisor.start_run(
            registration,
            service,
            body.request.to_application(),
            operation_id=body.operation_id,
            expected_review_context_hash=body.expected_review_context_hash,
            evaluation_service=evaluation_service(registration_id, registry, dependencies),
        )
        response.headers["Location"] = result.progress_path
        return Success(data=RunAcceptedDTO(**result.__dict__))

    @router.get(
        "/projects/{registration_id}/runs",
        response_model=Success[RunPageDTO],
        operation_id="listRuns",
    )
    async def list_runs(
        registration_id: str,
        decision_id: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Success[RunPageDTO]:
        service = execution_service(registration_id, dependencies, registry)
        page = await workers.run_sync(
            service.list, decision_id=decision_id, status=status, cursor=cursor, limit=limit
        )
        return Success(
            data=RunPageDTO(
                items=tuple(run_progress(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/runs/{run_id}",
        response_model=Success[RunProgressDTO],
        operation_id="readRun",
    )
    async def read_run(registration_id: str, run_id: str) -> Success[RunProgressDTO]:
        service = execution_service(registration_id, dependencies, registry)
        value = await workers.run_sync(service.show, run_id)
        return Success(data=run_progress(value))

    @router.post(
        "/projects/{registration_id}/runs/{run_id}/cancel",
        response_model=Success[RunProgressDTO],
        operation_id="cancelRun",
    )
    async def cancel_run(
        registration_id: str, run_id: str, body: RunCancelRequest
    ) -> Success[RunProgressDTO]:
        service = execution_service(registration_id, dependencies, registry)
        value = await workers.run_sync(service.cancel, run_id, operation_id=body.operation_id)
        return Success(data=run_progress(value))

    @router.post(
        "/projects/{registration_id}/runs/{run_id}/resume-preview",
        response_model=Success[RunResumePreviewDTO],
        operation_id="previewRunResume",
    )
    async def preview_run_resume(
        registration_id: str,
        run_id: str,
        body: VersionRequest,
        retry_unknown: Literal["true", "false"] = "false",
        max_attempts: str | None = None,
    ) -> Success[RunResumePreviewDTO]:
        del body
        service = execution_service(registration_id, dependencies, registry)
        attempt_limit = (
            query_decimal(
                max_attempts,
                reason="invalid_cap_extension",
                minimum=1,
                maximum=9007199254740991,
            )
            if max_attempts is not None
            else None
        )
        value = await workers.run_sync(
            service.preview_resume,
            run_id,
            retry_unknown=retry_unknown == "true",
            max_attempts=attempt_limit,
        )
        return Success(data=run_resume_preview(value))

    @router.post(
        "/projects/{registration_id}/runs/{run_id}/resume",
        response_model=Success[RunAcceptedDTO],
        status_code=202,
        operation_id="resumeRun",
        responses={202: {"headers": {"Location": {"schema": {"type": "string"}}}}},
    )
    async def resume_run(
        registration_id: str, run_id: str, body: RunResumeRequest, response: Response
    ) -> Success[RunAcceptedDTO]:
        registration = registry.require(registration_id)
        service = execution_service(registration_id, dependencies, registry)
        value = await supervisor.resume_run(
            registration,
            service,
            run_id,
            operation_id=body.operation_id,
            retry_unknown=body.retry_unknown,
            max_attempts=body.max_attempts,
            evaluation_service=evaluation_service(registration_id, registry, dependencies),
        )
        response.headers["Location"] = value.progress_path
        return Success(data=RunAcceptedDTO(**value.__dict__))
