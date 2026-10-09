"""Saved comparison creation, pagination and reads."""

from typing import cast

from fastapi import APIRouter, Query

from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Success
from deykit.api.dto.comparisons import (
    ComparisonDTO,
    ComparisonPageDTO,
    CreateComparisonRequest,
)
from deykit.api.projections import exact_display_tree
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.application.comparisons import ComparisonService, ComparisonView


def _dto(value: ComparisonView) -> ComparisonDTO:
    record = value.record
    return ComparisonDTO(
        comparison_id=record.id,
        left_evaluation_id=record.left_evaluation_id,
        right_evaluation_id=record.right_evaluation_id,
        left_result_snapshot_id=record.left_result_snapshot_id,
        right_result_snapshot_id=record.right_result_snapshot_id,
        outcomes=cast(
            dict[str, object], exact_display_tree(value.outcomes.model_dump(mode="python"))
        ),
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
    def service(registration_id: str) -> ComparisonService:
        return ComparisonService(
            registry.require(registration_id).source,
            dependencies.clock,
            dependencies.id_factory,
        )

    @router.post(
        "/projects/{registration_id}/comparisons",
        response_model=Success[ComparisonDTO],
        operation_id="createComparison",
    )
    async def create_comparison(
        registration_id: str, body: CreateComparisonRequest
    ) -> Success[ComparisonDTO]:
        value = await workers.run_sync(
            service(registration_id).create,
            body.left_evaluation_id,
            body.right_evaluation_id,
            operation_id=body.operation_id,
        )
        return Success(data=_dto(value))

    @router.get(
        "/projects/{registration_id}/comparisons",
        response_model=Success[ComparisonPageDTO],
        operation_id="listComparisons",
    )
    async def list_comparisons(
        registration_id: str,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Success[ComparisonPageDTO]:
        value = await workers.run_sync(service(registration_id).list, cursor=cursor, limit=limit)
        return Success(
            data=ComparisonPageDTO(
                items=tuple(_dto(item) for item in value.items),
                total=str(value.total),
                next_cursor=value.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/comparisons/{comparison_id}",
        response_model=Success[ComparisonDTO],
        operation_id="readComparison",
    )
    async def read_comparison(registration_id: str, comparison_id: str) -> Success[ComparisonDTO]:
        value = await workers.run_sync(service(registration_id).read, comparison_id)
        return Success(data=_dto(value))
