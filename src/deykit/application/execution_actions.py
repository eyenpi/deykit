"""Settlement of durable execution actions and their bound evaluations."""

from dataclasses import dataclass
from typing import Literal

from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService, EvaluationView
from deykit.contracts.errors import ServiceError
from deykit.runner.views import RunProgress


@dataclass(frozen=True)
class ExecutionActionResult:
    operation_id: str
    run: RunProgress
    evaluation_id: str | None
    evaluation_result_snapshot_id: str | None
    evaluation_replayed: bool | None
    evaluation_pending: bool
    evaluation_error: ServiceError | None
    warnings: tuple[ServiceError, ...]
    exit_code: Literal[0, 3, 4]


def settle_execution(
    evaluations: EvaluationService, result: RunProgress, operation_id: str
) -> ExecutionActionResult:
    """Score a settled run once, preserving the action's first evaluation binding."""
    error: ServiceError | None = None
    evaluation: EvaluationView | None = None
    try:
        if result.latest_result_snapshot_id is None:
            raise ServiceFailure(
                ServiceError(code="internal_error", reason="result_snapshot_missing")
            )
        evaluation = evaluations.evaluate_execution(
            result.run_id,
            result.latest_result_snapshot_id,
            execution_operation_id=operation_id,
            allow_create=not result.execution_active,
        )
    except Exception as failure:
        error = ServiceError(
            code=failure.error.code if isinstance(failure, ServiceFailure) else "internal_error",
            reason=failure.error.reason
            if isinstance(failure, ServiceFailure)
            else "evaluation_failed",
            resource_id=result.run_id,
        )

    if error is not None:
        if result.exit_code not in (3, 4):
            raise ServiceFailure(error) from None
        return ExecutionActionResult(
            operation_id=operation_id,
            run=result,
            evaluation_id=None,
            evaluation_result_snapshot_id=None,
            evaluation_replayed=None,
            evaluation_pending=False,
            evaluation_error=error,
            warnings=(error,),
            exit_code=result.exit_code,
        )

    if evaluation is None:
        return ExecutionActionResult(
            operation_id=operation_id,
            run=result,
            evaluation_id=None,
            evaluation_result_snapshot_id=None,
            evaluation_replayed=None,
            evaluation_pending=True,
            evaluation_error=None,
            warnings=(),
            exit_code=result.exit_code,
        )

    return ExecutionActionResult(
        operation_id=operation_id,
        run=result,
        evaluation_id=evaluation.record.id,
        evaluation_result_snapshot_id=evaluation.record.result_snapshot_id,
        evaluation_replayed=evaluation.replayed,
        evaluation_pending=False,
        evaluation_error=None,
        warnings=(),
        exit_code=result.exit_code,
    )
