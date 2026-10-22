"""Protected, read-only previews compiled from the registered project source."""

from typing import Literal

from fastapi import APIRouter

from deykit.api.dependencies import ApiDependencies
from deykit.application.checks import CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.execution import ExecutionService
from deykit.application.execution_review import ReviewedRunPreview
from deykit.runner.group_models import GroupPreview
from deykit.runner.views import RunPreview

from ..dto.common import Success
from ..dto.execution import (
    CheckPreviewRequest,
    ChoiceOrderPreviewRequest,
    ExecutionSettingsViewDTO,
    GroupMemberPreviewDTO,
    GroupPreviewDTO,
    MemberIdentityDTO,
    RequestIdentityDTO,
    ReviewSourceRecordDTO,
    RunCaseReviewDTO,
    RunPreviewDTO,
    RunPreviewRequest,
    RunPreviewSummaryDTO,
    RunReviewContextDTO,
)
from ..registry import ProjectRegistry
from ..runtime import TrackedWorkers


def _run(value: RunPreview) -> RunPreviewSummaryDTO:
    return RunPreviewSummaryDTO(
        decision_id=value.decision_id,
        dataset_id=value.dataset_id,
        mode=value.mode,
        provider_id=value.provider_id,
        fixture_set_id=value.fixture_set_id,
        requested_model=value.requested_model,
        selected_case_ids=value.selected_case_ids,
        initial_requests=str(value.initial_requests),
        invalid_cases=value.invalid_cases,
        settings=ExecutionSettingsViewDTO.from_application(value.settings),
        development_case_count=str(value.development_case_count),
        review_context_hash=value.review_context_hash,
        dry_run=value.dry_run,
        semantic_headers_sources=value.semantic_headers_sources,
    )


def _reviewed_run(value: ReviewedRunPreview) -> RunPreviewDTO:
    summary = _run(value.preview)
    context = value.review_context
    return RunPreviewDTO(
        **summary.model_dump(),
        review_context=RunReviewContextDTO(
            definition_source=context.definition_source,
            revision_id=context.revision_id,
            definition_hash=context.definition_hash,
            source_context_hash=context.source_context_hash,
            provider_id=context.provider_id,
            destination=context.destination,
            adapter=context.adapter,
            requested_model=context.requested_model,
            compiler_id=context.compiler_id,
            compiler_version=context.compiler_version,
            fixture_set_id=context.fixture_set_id,
            source_records=tuple(
                ReviewSourceRecordDTO(
                    collection=item.collection,
                    scope=item.scope,
                    resource_id=item.resource_id,
                    etag=item.etag,
                    body_hash=item.body_hash,
                )
                for item in context.source_records
            ),
            development_case_ids=context.development_case_ids,
            development_label_count=str(context.development_label_count),
        ),
        case_reviews=tuple(
            RunCaseReviewDTO(
                case_id=item.case_id,
                input_hash=item.input_hash,
                request_hash=item.request_hash,
                compiler=item.compiler,
                compiler_version=item.compiler_version,
                requested_model=item.requested_model,
                input_error=item.input_error,
                request_source=item.request_source,
                request_source_redacted=item.request_source_redacted,
                semantic_headers_source=item.semantic_headers_source,
            )
            for item in value.case_reviews
        ),
    )


def _group(value: GroupPreview) -> GroupPreviewDTO:
    if len(value.members) != len(value.identities):
        raise RuntimeError("preview_identity_count_mismatch")
    return GroupPreviewDTO(
        kind=value.kind,
        members=tuple(
            GroupMemberPreviewDTO(
                preview=_run(preview),
                identity=MemberIdentityDTO(
                    option_order=identity.option_order,
                    requests=tuple(
                        RequestIdentityDTO(
                            case_id=item.case_id,
                            input_hash=item.input_hash,
                            request_hash=item.request_hash,
                            compiler=item.compiler,
                            compiler_version=item.compiler_version,
                            requested_model=item.requested_model,
                            semantic_headers_source=item.semantic_headers_source,
                        )
                        for item in identity.requests
                    ),
                    run_id=identity.run_id,
                ),
            )
            for preview, identity in zip(value.members, value.identities, strict=True)
        ),
        initial_requests=str(value.initial_requests),
        attempt_limit=str(value.attempt_limit),
        deadline_seconds=str(value.deadline_seconds),
        review_context_hash=value.review_context_hash,
        dry_run=value.dry_run,
        independent_case_count=str(value.independent_case_count),
        algorithm=value.algorithm,
        seed=str(value.seed) if value.seed is not None else None,
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def execution_service(registration_id: str) -> ExecutionService:
        source = registry.require(registration_id).source
        return ExecutionService(
            source,
            source,
            dependencies.backends_factory(source, dependencies.clock),
            dependencies.clock,
            dependencies.id_factory,
        )

    @router.post(
        "/projects/{registration_id}/runs/preview",
        response_model=Success[RunPreviewDTO],
        operation_id="previewRun",
    )
    async def run_preview(
        registration_id: str,
        body: RunPreviewRequest,
        include_request: Literal["true", "false"] = "false",
    ) -> Success[RunPreviewDTO]:
        service = execution_service(registration_id)
        preview = await workers.run_sync(
            service.review_preview,
            body.request.to_application(),
            include_request_source=include_request == "true",
        )
        return Success(data=_reviewed_run(preview))

    @router.post(
        "/projects/{registration_id}/diagnostics/choice-order/preview",
        response_model=Success[GroupPreviewDTO],
        operation_id="previewChoiceOrder",
    )
    async def choice_order_preview(
        registration_id: str, body: ChoiceOrderPreviewRequest
    ) -> Success[GroupPreviewDTO]:
        service = DiagnosticService(execution_service(registration_id))
        request = ChoiceOrderRequest(
            run=body.request.run.to_application(),
            orders=body.request.orders,
            seed=int(body.request.seed),
        )
        preview = await workers.run_sync(service.preview, request)
        return Success(data=_group(preview))

    @router.post(
        "/projects/{registration_id}/checks/preview",
        response_model=Success[GroupPreviewDTO],
        operation_id="previewRegressionCheck",
    )
    async def check_preview(
        registration_id: str, body: CheckPreviewRequest
    ) -> Success[GroupPreviewDTO]:
        service = CheckService(execution_service(registration_id))
        preview = await workers.run_sync(service.preview, body.request.to_application())
        return Success(data=_group(preview))
