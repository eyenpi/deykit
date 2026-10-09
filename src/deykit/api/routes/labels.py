"""Decision-scoped label review, history, and atomic batch routes."""

from typing import Literal, cast

from fastapi import APIRouter

from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.dto.common import Success
from deykit.api.dto.labels import (
    LabelBatchDTO,
    LabelBatchRequest,
    LabelEditDTO,
    LabelHistoryDTO,
    LabelPageDTO,
    LabelReviewDTO,
    LabelViewDTO,
)
from deykit.api.query import decimal
from deykit.api.registry import ProjectRegistry
from deykit.api.runtime import TrackedWorkers
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelEdit, LabelReview, LabelService, LabelView
from deykit.contracts.errors import ServiceError


def _invalid(reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason=reason))


def _limit(value: str | None) -> int:
    if value is None:
        return 50
    return decimal(value, reason="invalid_integer_query", minimum=1, maximum=500)


def _review(value: LabelReview) -> LabelReviewDTO:
    return LabelReviewDTO(
        decision_id=value.decision_id,
        dataset_id=value.dataset_id,
        case_id=value.case_id,
        question_id=value.question_id,
        input_hash=value.input_hash,
        decision_etag=value.decision_etag,
        draft_etag=value.draft_etag,
        label_etag=value.label_etag,
    )


def _view(value: LabelView) -> LabelViewDTO:
    return LabelViewDTO(
        review=_review(value.review),
        case=value.case,
        definition=value.definition,
        label=value.label,
        reasons=value.reasons,
        missing_option_ids=value.missing_option_ids,
        status=cast(Literal["unlabelled", "excluded", "applicable"], value.status),
    )


def _edit(value: LabelEditDTO) -> LabelEdit:
    r = value.review
    return LabelEdit(
        LabelReview(
            decision_id=r.decision_id,
            dataset_id=r.dataset_id,
            case_id=r.case_id,
            question_id=r.question_id,
            input_hash=r.input_hash,
            decision_etag=r.decision_etag,
            draft_etag=r.draft_etag,
            label_etag=r.label_etag,
        ),
        value.action,
        value.acceptable_option_ids,
        value.provenance,
        value.note,
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def service_for(registration_id: str) -> LabelService:
        source: ApiProjectSource = registry.require(registration_id).source
        return LabelService(source, dependencies.clock, dependencies.id_factory)

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels",
        response_model=Success[LabelPageDTO],
    )
    async def list_labels(
        registration_id: str,
        decision_id: str,
        dataset_id: str,
        status: str | None = None,
        cursor: str | None = None,
        limit: str | None = None,
    ) -> Success[LabelPageDTO]:
        result = await workers.run_sync(
            service_for(registration_id).list,
            decision_id,
            dataset_id,
            status=status,
            cursor=cursor,
            limit=_limit(limit),
        )
        return Success(
            data=LabelPageDTO(
                items=tuple(_view(item) for item in result.items),
                total=str(result.total),
                next_cursor=result.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/"
        "{case_id}",
        response_model=Success[LabelViewDTO],
    )
    async def read_label(
        registration_id: str,
        decision_id: str,
        dataset_id: str,
        case_id: str,
        question_id: str | None = None,
    ) -> Success[LabelViewDTO]:
        value = await workers.run_sync(
            service_for(registration_id).read,
            decision_id,
            dataset_id,
            case_id,
            question_id=question_id,
        )
        return Success(data=_view(value))

    @router.get(
        "/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/"
        "{case_id}/history",
        response_model=Success[LabelHistoryDTO],
    )
    async def label_history(
        registration_id: str,
        decision_id: str,
        dataset_id: str,
        case_id: str,
        question_id: str | None = None,
    ) -> Success[LabelHistoryDTO]:
        items = await workers.run_sync(
            service_for(registration_id).history,
            decision_id,
            dataset_id,
            case_id,
            question_id=question_id,
        )
        return Success(data=LabelHistoryDTO(items=items))

    @router.post(
        "/projects/{registration_id}/decisions/{decision_id}/datasets/{dataset_id}/labels/batch",
        response_model=Success[LabelBatchDTO],
    )
    async def batch_labels(
        registration_id: str,
        decision_id: str,
        dataset_id: str,
        body: LabelBatchRequest,
    ) -> Success[LabelBatchDTO]:
        edits = tuple(_edit(edit) for edit in body.edits)
        if any(
            edit.review.decision_id != decision_id or edit.review.dataset_id != dataset_id
            for edit in edits
        ):
            raise _invalid("label_route_scope_mismatch")
        result = await workers.run_sync(
            service_for(registration_id).batch,
            edits,
            operation_id=body.operation_id,
        )
        return Success(data=LabelBatchDTO(changes=result.changes, replayed=result.replayed))
