"""Explicit regression oracle creation and append-only removal."""

from fastapi import APIRouter

from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Success
from deykit.api.dto.regressions import (
    AddRegressionRequest,
    RegressionDTO,
    RegressionPageDTO,
    RemoveRegressionRequest,
)
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.application.errors import ServiceFailure
from deykit.application.regressions import RegressionService, RegressionView
from deykit.contracts.errors import ServiceError


def _dto(value: RegressionView) -> RegressionDTO:
    return RegressionDTO(
        regression_id=value.id,
        decision_id=value.decision_id,
        dataset_id=value.dataset_id,
        case_id=value.case_id,
        question_id=value.question_id,
        acceptable_option_ids=value.acceptable_option_ids,
        reason=value.reason,
        original_split=value.original_split,
        provenance=value.provenance,
        source_run_id=value.source_run_id,
        source_result_snapshot_id=value.source_result_snapshot_id,
        input_hash=value.input_hash,
        removed=value.removed,
        executable=value.executable,
        unavailable_reason=value.unavailable_reason,
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def service(registration_id: str) -> RegressionService:
        return RegressionService(
            registry.require(registration_id).source,
            dependencies.clock,
            dependencies.id_factory,
        )

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/regressions",
        response_model=Success[RegressionPageDTO],
        operation_id="listRegressions",
    )
    async def list_regressions(
        registration_id: str, decision_id: str
    ) -> Success[RegressionPageDTO]:
        values = await workers.run_sync(service(registration_id).list, decision_id)
        return Success(data=RegressionPageDTO(items=tuple(_dto(item) for item in values)))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/regressions",
        response_model=Success[RegressionDTO],
        operation_id="addRegression",
    )
    async def add_regression(
        registration_id: str, decision_id: str, body: AddRegressionRequest
    ) -> Success[RegressionDTO]:
        value = await workers.run_sync(
            service(registration_id).add,
            body.to_application(),
            operation_id=body.operation_id,
            expected_decision_id=decision_id,
        )
        return Success(data=_dto(value))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/regressions/{regression_id}/remove",
        response_model=Success[RegressionDTO],
        operation_id="removeRegression",
    )
    async def remove_regression(
        registration_id: str,
        decision_id: str,
        regression_id: str,
        body: RemoveRegressionRequest,
    ) -> Success[RegressionDTO]:
        if body.decision_id != decision_id:
            raise ServiceFailure(
                ServiceError(
                    code="validation_error",
                    reason="regression_decision_mismatch",
                    resource_id=decision_id,
                )
            )
        value = await workers.run_sync(
            service(registration_id).remove,
            regression_id,
            decision_id=decision_id,
            operation_id=body.operation_id,
        )
        return Success(data=_dto(value))
