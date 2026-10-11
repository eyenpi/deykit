"""Frozen result inspections, evaluations and append-only annotations."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Query

from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Success
from deykit.api.dto.results import (
    AddAnnotationRequest,
    AnnotationDTO,
    AnnotationPageDTO,
    AssessmentCountsDTO,
    CaseDetailDTO,
    EvaluateRequest,
    EvaluationDTO,
    EvaluationPageDTO,
    ProbabilityRowDTO,
    ReevaluateRequest,
    ResultContextDTO,
    ResultPageDTO,
    ResultRowDTO,
)
from deykit.api.projections import exact_display_tree
from deykit.api.registry import ProjectRegistry
from deykit.api.routes.execution import evaluation_service
from deykit.api.runtime import TrackedWorkers
from deykit.application.annotations import AnnotationService, StoredAnnotation
from deykit.application.evaluations import EvaluationView
from deykit.application.results import ResultContext, ResultInspection


def _evaluation(value: EvaluationView) -> EvaluationDTO:
    record = value.record
    return EvaluationDTO(
        evaluation_id=record.id,
        run_id=record.run_id,
        result_snapshot_id=record.result_snapshot_id,
        label_snapshot_id=record.label_snapshot_id,
        mode=record.mode,
        metrics_source=record.metrics_source,
        metrics=cast(dict[str, object], exact_display_tree(value.metrics)),
        content_hash=record.content_hash,
        created_at=record.created_at,
        execution_operation_id=record.execution_operation_id,
        replayed=value.replayed,
    )


def _annotation(value: StoredAnnotation) -> AnnotationDTO:
    record = value.annotation
    return AnnotationDTO(
        annotation_id=record.id,
        run_id=record.run_id,
        case_id=record.case_id,
        note=record.note,
        content_hash=record.content_hash,
        created_at=record.created_at,
        replayed=value.replayed,
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def inspection(registration_id: str) -> ResultInspection:
        return ResultInspection(registry.require(registration_id).source)

    def annotations(registration_id: str) -> AnnotationService:
        return AnnotationService(
            registry.require(registration_id).source,
            dependencies.clock,
            dependencies.id_factory,
        )

    def result_context(value: ResultContext) -> ResultContextDTO:
        return ResultContextDTO.model_validate(
            {
                **cast(dict[str, object], exact_display_tree(value.source())),
                "through_event_sequence": str(value.through_event_sequence),
            }
        )

    @router.get(
        "/projects/{registration_id}/runs/{run_id}/results",
        response_model=Success[ResultPageDTO],
        operation_id="listResults",
    )
    async def list_results(
        registration_id: str,
        run_id: str,
        evaluation_id: str | None = None,
        status: str | None = None,
        split: Literal["development", "calibration", "test"] | None = None,
        tag: str | None = None,
        assessment_filter: Literal["all", "inspect", "incorrect", "unlabelled"] = "all",
        expected_result_snapshot_id: str | None = None,
        expected_label_snapshot_id: str | None = None,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Success[ResultPageDTO]:
        value = await workers.run_sync(
            inspection(registration_id).list,
            run_id,
            evaluation_id=evaluation_id,
            status=status,
            split=split,
            tag=tag,
            assessment_filter=assessment_filter,
            expected_result_snapshot_id=expected_result_snapshot_id,
            expected_label_snapshot_id=expected_label_snapshot_id,
            cursor=cursor,
            limit=limit,
        )
        return Success(
            data=ResultPageDTO(
                run_id=value.run_id,
                result_snapshot_id=value.result_snapshot_id,
                label_snapshot_id=value.label_snapshot_id,
                evaluation_id=value.evaluation_id,
                selected_count=str(value.selected_count),
                status_counts={key: str(count) for key, count in value.status_counts.items()},
                summary=cast(dict[str, object], exact_display_tree(value.summary)),
                filtered_count=str(value.filtered_count),
                assessment_counts=AssessmentCountsDTO(
                    all=str(value.assessment_counts.all),
                    inspect=str(value.assessment_counts.inspect),
                    incorrect=str(value.assessment_counts.incorrect),
                    unlabelled=str(value.assessment_counts.unlabelled),
                ),
                context=result_context(value.context),
                items=tuple(
                    ResultRowDTO(source=cast(dict[str, object], exact_display_tree(item.source())))
                    for item in value.items
                ),
                next_cursor=value.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/runs/{run_id}/results/{case_id}",
        response_model=Success[CaseDetailDTO],
        operation_id="readResult",
    )
    async def read_result(
        registration_id: str,
        run_id: str,
        case_id: str,
        evaluation_id: str | None = None,
        expected_result_snapshot_id: str | None = None,
        expected_label_snapshot_id: str | None = None,
        include_input: Literal["true", "false"] = "false",
        include_request: Literal["true", "false"] = "false",
        include_response: Literal["true", "false"] = "false",
        include_attempts: Literal["true", "false"] = "false",
    ) -> Success[CaseDetailDTO]:
        value = await workers.run_sync(
            inspection(registration_id).show,
            run_id,
            case_id,
            evaluation_id=evaluation_id,
            expected_result_snapshot_id=expected_result_snapshot_id,
            expected_label_snapshot_id=expected_label_snapshot_id,
            include_input=include_input == "true",
            include_request=include_request == "true",
            include_response=include_response == "true",
            include_attempts=include_attempts == "true",
        )
        return Success(
            data=CaseDetailDTO(
                source=cast(dict[str, object], exact_display_tree(value.source())),
                context=result_context(value.context),
                case_input_hash=value.case_input_hash,
                probabilities=tuple(
                    ProbabilityRowDTO(**item.source()) for item in value.probabilities
                ),
                probabilities_unavailable_reason=value.probabilities_unavailable_reason,
            )
        )

    @router.post(
        "/projects/{registration_id}/runs/{run_id}/evaluations",
        response_model=Success[EvaluationDTO],
        operation_id="createEvaluation",
    )
    async def evaluate(
        registration_id: str, run_id: str, body: EvaluateRequest
    ) -> Success[EvaluationDTO]:
        service = evaluation_service(registration_id, registry, dependencies)
        value = await workers.run_sync(
            service.evaluate_saved,
            run_id,
            body.result_snapshot_id,
            label_snapshot_id=body.label_snapshot_id,
            mode=body.mode,
            operation_id=body.operation_id,
        )
        return Success(data=_evaluation(value))

    @router.get(
        "/projects/{registration_id}/runs/{run_id}/evaluations",
        response_model=Success[EvaluationPageDTO],
        operation_id="listEvaluations",
    )
    async def list_evaluations(
        registration_id: str,
        run_id: str,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Success[EvaluationPageDTO]:
        value = await workers.run_sync(
            evaluation_service(registration_id, registry, dependencies).list,
            run_id,
            cursor=cursor,
            limit=limit,
        )
        return Success(
            data=EvaluationPageDTO(
                items=tuple(_evaluation(item) for item in value.items),
                total=str(value.total),
                next_cursor=value.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/evaluations/{evaluation_id}",
        response_model=Success[EvaluationDTO],
        operation_id="readEvaluation",
    )
    async def read_evaluation(registration_id: str, evaluation_id: str) -> Success[EvaluationDTO]:
        value = await workers.run_sync(
            evaluation_service(registration_id, registry, dependencies).read, evaluation_id
        )
        return Success(data=_evaluation(value))

    @router.post(
        "/projects/{registration_id}/runs/{run_id}/reevaluations",
        response_model=Success[EvaluationDTO],
        operation_id="reevaluateRun",
    )
    async def reevaluate(
        registration_id: str, run_id: str, body: ReevaluateRequest
    ) -> Success[EvaluationDTO]:
        value = await workers.run_sync(
            evaluation_service(registration_id, registry, dependencies).reevaluate_current_labels,
            run_id,
            body.result_snapshot_id,
            operation_id=body.operation_id,
        )
        return Success(data=_evaluation(value))

    @router.get(
        "/projects/{registration_id}/runs/{run_id}/annotations",
        response_model=Success[AnnotationPageDTO],
        operation_id="listAnnotations",
    )
    async def list_annotations(
        registration_id: str,
        run_id: str,
        case_id: str | None = None,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Success[AnnotationPageDTO]:
        value = await workers.run_sync(
            annotations(registration_id).list,
            run_id,
            case_id=case_id,
            cursor=cursor,
            limit=limit,
        )
        return Success(
            data=AnnotationPageDTO(
                items=tuple(_annotation(item) for item in value.items),
                total=str(value.total),
                next_cursor=value.next_cursor,
            )
        )

    @router.post(
        "/projects/{registration_id}/runs/{run_id}/annotations",
        response_model=Success[AnnotationDTO],
        operation_id="addAnnotation",
    )
    async def add_annotation(
        registration_id: str, run_id: str, body: AddAnnotationRequest
    ) -> Success[AnnotationDTO]:
        value = await workers.run_sync(
            annotations(registration_id).add,
            run_id,
            body.case_id,
            body.note,
            operation_id=body.operation_id,
        )
        return Success(data=_annotation(value))

    @router.get(
        "/projects/{registration_id}/annotations/{annotation_id}",
        response_model=Success[AnnotationDTO],
        operation_id="readAnnotation",
    )
    async def read_annotation(registration_id: str, annotation_id: str) -> Success[AnnotationDTO]:
        value = await workers.run_sync(annotations(registration_id).read, annotation_id)
        return Success(data=_annotation(value))
