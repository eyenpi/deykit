"""Independent checks for frozen result filters, pins and probability display."""

import asyncio
from itertools import count
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from deykit.api.assets import AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.errors import TransportFailure, error_response
from deykit.api.routes.results import register as register_result_routes
from deykit.api.security import LocalBoundary
from deykit.api.session import SessionCapability
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.labels import LabelService
from deykit.application.results import ResultInspection
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonDocument
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    DispatchOutcome,
    ExecutionSettings,
    LabelRecord,
    NormalizedAnswer,
    ResultSnapshot,
)
from deykit.domain.label_identity import label_id
from deykit.runner.planner import RunRequest


def _request():
    return RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )


class _Workers:
    async def run_sync(self, function, *args, **kwargs):
        return function(*args, **kwargs)


def _result_api(source, clock):
    origin = "http://127.0.0.1:8769"
    config = LocalServerConfig(
        "127.0.0.1:8769", origin, AssetCatalog.from_package()
    )
    session = SessionCapability.create()
    app = FastAPI(redirect_slashes=False)

    @app.exception_handler(RequestValidationError)
    async def request_invalid(_request: Request, _error: RequestValidationError):
        return error_response(TransportFailure(422, "validation_error", "invalid_request"))

    @app.exception_handler(HTTPException)
    async def http_invalid(_request: Request, _error: HTTPException):
        return error_response(TransportFailure(404, "not_found", "route_not_found"))

    @app.exception_handler(Exception)
    async def service_error(_request: Request, error: Exception):
        return error_response(error)

    router = APIRouter(prefix="/api/v1")
    dependencies = SimpleNamespace(clock=clock, id_factory=lambda: "m12-api-id")
    registry = SimpleNamespace(require=lambda _registration: SimpleNamespace(source=source))
    register_result_routes(router, dependencies, registry, _Workers())
    app.include_router(router)
    return LocalBoundary(app, config, session), session.token, origin


def test_assessment_filter_counts_are_global_and_paired_pins_reject_drift(setup, monkeypatch):
    source, runner, factory, clock = setup(4, invalid=(3,))
    labels = LabelService(source, clock, lambda: "label-change")
    review = labels.read("decision", "data", "case-00").review
    labels.set(review, ("yes",), provenance="human", operation_id="label-case-00")
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(question_id="q", option_id="no", reported_model="authored-v1"),
            raw_response_source=(
                '{"answers":{"q":{"option_id":"no"}},'
                '"Authorization":"Bearer m12-private"}'
            ),
        )
    ]
    factory.responses["case-02"] = [
        DispatchOutcome(
            state="unknown",
            error=ServiceError(code="provider_rejected", reason="disconnect"),
        )
    ]
    run = asyncio.run(runner.start(_request(), operation_id="start"))
    inspection = ResultInspection(source)

    calls = 0
    capture = source.capture_snapshot

    def counted_capture():
        nonlocal calls
        calls += 1
        return capture()

    monkeypatch.setattr(source, "capture_snapshot", counted_capture)
    first = inspection.list(run.run_id, assessment_filter="incorrect", limit=1)
    assert calls == 1
    assert first.filtered_count == 1 and first.items[0].case.id == "case-00"
    assert first.assessment_counts.all == 4
    assert first.assessment_counts.incorrect == 1
    assert first.assessment_counts.inspect == 3
    assert first.assessment_counts.unlabelled == 1
    pinned_detail = inspection.show(
        run.run_id,
        "case-00",
        expected_result_snapshot_id=first.result_snapshot_id,
        expected_label_snapshot_id=first.label_snapshot_id,
        include_attempts=True,
        include_request=True,
        include_response=True,
    )
    assert calls == 2
    assert len(pinned_detail.attempts) == 1
    assert pinned_detail.case_input_hash == JsonDocument(
        pinned_detail.row.case.input_source
    ).content_hash
    assert "m12-private" not in repr(pinned_detail.source())
    assert "[REDACTED]" in cast(str, pinned_detail.attempts[0]["response_source"])
    assert inspection.list(
        run.run_id,
        assessment_filter="all",
        expected_result_snapshot_id=first.result_snapshot_id,
        expected_label_snapshot_id=first.label_snapshot_id,
        limit=1,
    ).context == first.context
    assert calls == 3

    with pytest.raises(ServiceFailure) as one_sided:
        inspection.list(run.run_id, expected_result_snapshot_id=first.result_snapshot_id)
    assert one_sided.value.error.reason == "result_context_selector_pair_required"
    with pytest.raises(ServiceFailure) as one_sided_detail:
        inspection.show(
            run.run_id,
            "case-00",
            expected_label_snapshot_id=first.label_snapshot_id,
        )
    assert one_sided_detail.value.error.reason == "result_context_selector_pair_required"
    with pytest.raises(ServiceFailure) as malformed_pin:
        inspection.show(
            run.run_id,
            "case-00",
            expected_result_snapshot_id="",
            expected_label_snapshot_id="",
        )
    assert malformed_pin.value.error.reason == "invalid_resource_id"
    with pytest.raises(ServiceFailure) as invalid_filter:
        inspection.list(run.run_id, assessment_filter="everything")
    assert invalid_filter.value.error.reason == "invalid_assessment_filter"

    latest = max(
        (
            ResultSnapshot.model_validate_json(
                source.read(ResourceKey("result_snapshots", key)).body
            )
            for key in source.list_ids("result_snapshots")
        ),
        key=lambda item: item.through_event_sequence,
    )
    saved = EvaluationService(source, clock, lambda: "saved-evaluation").evaluate_saved(
        run.run_id, latest.id, operation_id="save-evaluation"
    )
    asyncio.run(
        runner.resume(run.run_id, operation_id="resume", retry_unknown=True)
    )
    with pytest.raises(ServiceFailure) as drift:
        inspection.list(
            run.run_id,
            expected_result_snapshot_id=first.result_snapshot_id,
            expected_label_snapshot_id=first.label_snapshot_id,
        )
    assert drift.value.error.reason == "result_context_changed"
    with pytest.raises(ServiceFailure) as detail_drift:
        inspection.show(
            run.run_id,
            "case-00",
            expected_result_snapshot_id=first.result_snapshot_id,
            expected_label_snapshot_id=first.label_snapshot_id,
            include_attempts=True,
            include_response=True,
        )
    assert detail_drift.value.error.reason == "result_context_changed"
    saved_page = inspection.list(run.run_id, evaluation_id=saved.record.id)
    assert saved_page.result_snapshot_id == latest.id
    assert saved_page.label_snapshot_id == saved.record.label_snapshot_id


def test_assessment_counts_precede_filtering_and_pagination_for_status_intersections(setup):
    source, runner, factory, _ = setup(12, invalid=(8,))
    for index in (9, 10, 11):
        key = ResourceKey("cases", f"case-{index:02}", ("data",))
        stored = source.read(key)
        assert stored is not None
        case = CaseRecord.model_validate_json(stored.body).model_copy(
            update={"split": "test", "tags": ("focus",)}
        )
        source.commit(
            f"mark-test-case-{index}",
            (SourceChange(key, dump_record(case), stored.etag),),
        )
    factory.responses["case-09"] = [
        DispatchOutcome(
            state="known",
            error=ServiceError(code="response_invalid", reason="invalid_choice"),
        )
    ]
    factory.responses["case-10"] = [
        DispatchOutcome(
            state="unknown",
            error=ServiceError(code="provider_rejected", reason="disconnect"),
        )
    ]
    request = RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
        settings=ExecutionSettings(max_attempts=90, concurrency=1),
    )

    def stop_after_unknown(progress):
        if progress.attempts_used == 10:
            runner.cancel(progress.run_id, operation_id="stop-after-unknown")

    run = asyncio.run(
        runner.start(request, operation_id="start-many", on_progress=stop_after_unknown)
    )
    inspection = ResultInspection(source)
    first = inspection.list(run.run_id, assessment_filter="inspect", limit=3)
    second = inspection.list(
        run.run_id,
        assessment_filter="inspect",
        limit=3,
        cursor=first.next_cursor,
    )
    assert first.filtered_count == second.filtered_count == 4
    assert first.assessment_counts == second.assessment_counts
    assert first.assessment_counts.all == 12
    assert first.assessment_counts.inspect == 4
    assert first.assessment_counts.incorrect == 0
    assert first.assessment_counts.unlabelled == 8
    assert len(first.items) == 3 and len(second.items) == 1
    assert {item.result.status for item in (*first.items, *second.items)} == {
        "input_invalid",
        "response_error",
        "unknown",
        "pending",
    }

    intersection = inspection.list(
        run.run_id, status="response_error", split="test", tag="focus"
    )
    assert intersection.filtered_count == 1
    assert intersection.items[0].case.id == "case-09"
    assert intersection.assessment_counts == type(intersection.assessment_counts)(1, 1, 0, 0)
    absent_intersection = inspection.list(
        run.run_id, status="valid", split="test", tag="focus"
    )
    assert absent_intersection.filtered_count == 0
    assert absent_intersection.assessment_counts.all == 0


def test_assessment_membership_keeps_disputed_stale_legacy_and_acceptable_sets_distinct(
    setup,
):
    source, runner, factory, clock = setup(7)
    label_ids = count()
    labels = LabelService(source, clock, lambda: f"label-m12-{next(label_ids)}")
    for case_id, expected in (
        ("case-00", ("yes",)),
        ("case-01", ("no",)),
        ("case-02", ("yes", "no")),
        ("case-03", ("yes",)),
        ("case-04", ("yes",)),
    ):
        review = labels.read("decision", "data", case_id).review
        labels.set(
            review,
            expected,
            provenance="human",
            operation_id=f"label-{case_id}",
        )
    disputed_review = labels.read("decision", "data", "case-03").review
    labels.dispute(disputed_review, reason="Two reviewers differ.", operation_id="dispute-case-03")

    legacy_case = source.read(ResourceKey("cases", "case-05", ("data",)))
    assert legacy_case is not None
    legacy = LabelRecord(
        id=label_id("case-05", "legacy-q"),
        decision_id="decision",
        dataset_id="data",
        case_id="case-05",
        question_id="legacy-q",
        input_hash=JsonDocument(
            CaseRecord.model_validate_json(legacy_case.body).input_source
        ).content_hash,
        acceptable_option_ids=("yes",),
        provenance="human",
        updated_at=clock.utc_now(),
    )
    legacy_key = ResourceKey("labels", legacy.id, ("decision", "data"))
    source.commit("legacy-label", (SourceChange(legacy_key, dump_record(legacy), None),))

    run = asyncio.run(runner.start(_request(), operation_id="start-assessment-membership"))
    changed_key = ResourceKey("cases", "case-04", ("data",))
    stored_case = source.read(changed_key)
    assert stored_case is not None
    changed_case = CaseRecord.model_validate_json(stored_case.body).model_copy(
        update={"input_source": '{"text":"Changed after the saved answer."}'}
    )
    source.commit(
        "change-case-after-run",
        (SourceChange(changed_key, dump_record(changed_case), stored_case.etag),),
    )
    current_review = labels.read("decision", "data", "case-04").review
    labels.set(
        current_review,
        ("yes",),
        provenance="human",
        operation_id="label-new-input-case-04",
    )
    latest = max(
        (
            ResultSnapshot.model_validate_json(
                source.read(ResourceKey("result_snapshots", key)).body
            )
            for key in source.list_ids("result_snapshots")
        ),
        key=lambda snapshot: snapshot.through_event_sequence,
    )
    evaluation = EvaluationService(
        source, clock, lambda: "current-label-evaluation"
    ).reevaluate_current_labels(
        run.run_id,
        latest.id,
        operation_id="evaluate-current-labels",
    )

    inspection = ResultInspection(source)
    incorrect = inspection.list(
        run.run_id,
        evaluation_id=evaluation.record.id,
        assessment_filter="incorrect",
    )
    inspect = inspection.list(
        run.run_id,
        evaluation_id=evaluation.record.id,
        assessment_filter="inspect",
    )
    unlabelled = inspection.list(
        run.run_id,
        evaluation_id=evaluation.record.id,
        assessment_filter="unlabelled",
    )
    assert [item.case.id for item in incorrect.items] == ["case-01"]
    assert [item.case.id for item in inspect.items] == ["case-01"]
    assert [item.case.id for item in unlabelled.items] == ["case-06"]
    assert incorrect.assessment_counts.all == 7
    assert incorrect.assessment_counts.incorrect == incorrect.assessment_counts.inspect == 1
    assert incorrect.assessment_counts.unlabelled == 1
    rows = {
        item.case.id: item
        for item in inspection.list(run.run_id, evaluation_id=evaluation.record.id).items
    }
    assert rows["case-02"].assessment.set_correct is True
    assert (
        "acceptable_set_excluded_from_class_metrics"
        in rows["case-02"].assessment.exclusion_reasons
    )
    assert "disputed" in rows["case-03"].assessment.exclusion_reasons
    assert "stale" in rows["case-04"].assessment.exclusion_reasons
    assert "incompatible_question_label" in rows["case-05"].assessment.exclusion_reasons


def test_probability_table_preserves_frozen_option_order_and_exact_decimal_text(setup):
    source, runner, factory, _ = setup(1)
    exact = "0.12345678901234567890123456789"
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(
                question_id="q",
                option_id="yes",
                probabilities_source=f'{{"no":0.4,"yes":{exact}}}',
                native_confidence_source="0.6",
                native_confidence_semantics="provider_reported",
                reported_model="authored-v1",
            ),
        )
    ]
    run = asyncio.run(runner.start(_request(), operation_id="start"))
    inspection = ResultInspection(source)
    detail = inspection.show(run.run_id, "case-00")
    assert [(row.option_id, row.option_name) for row in detail.probabilities] == [
        ("yes", "Yes"),
        ("no", "No"),
    ]
    assert detail.probabilities[0].probability == exact
    assert detail.probabilities_unavailable_reason is None
    assert detail.answer["probabilities_source"] == f'{{"no":0.4,"yes":{exact}}}'
    assert detail.answer["native_confidence_source"] == "0.6"
    assert detail.case_input_hash

    absent_source, absent_runner, _, _ = setup(1)
    absent_run = asyncio.run(absent_runner.start(_request(), operation_id="start-absent"))
    absent = ResultInspection(absent_source).show(absent_run.run_id, "case-00")
    assert absent.probabilities == ()
    assert absent.probabilities_unavailable_reason == "probabilities_not_provided"

    malformed_source, malformed_runner, malformed_factory, _ = setup(1)
    malformed_factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(
                question_id="q",
                option_id="yes",
                probabilities_source='{"yes":"high","no":0}',
                reported_model="authored-v1",
            ),
        )
    ]
    malformed_run = asyncio.run(malformed_runner.start(_request(), operation_id="start-malformed"))
    malformed = ResultInspection(malformed_source).show(malformed_run.run_id, "case-00")
    assert malformed.probabilities == ()
    assert malformed.probabilities_unavailable_reason == "invalid_probability_source"


def test_result_http_routes_enforce_typed_pins_and_query_admission(setup):
    source, runner, factory, clock = setup(1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(
                question_id="q",
                option_id="yes",
                probabilities_source='{"yes":0.75,"no":0.25}',
                reported_model="authored-v1",
            ),
            raw_response_source='{"Authorization":"Bearer transport-private"}',
        )
    ]
    run = asyncio.run(runner.start(_request(), operation_id="api-start"))
    boundary, capability, origin = _result_api(source, clock)
    headers = {"x-deykit-capability": capability, "origin": origin}
    base = f"/api/v1/projects/reg-1/runs/{run.run_id}/results"
    captures = 0
    commits = []
    original_capture = source.capture_snapshot
    original_commit = source.commit

    def counted_capture():
        nonlocal captures
        captures += 1
        return original_capture()

    def counted_commit(*args, **kwargs):
        commits.append((args, kwargs))
        return original_commit(*args, **kwargs)

    source.capture_snapshot = counted_capture
    source.commit = counted_commit

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=boundary), base_url=origin
        ) as client:
            first = await client.get(base, headers=headers)
            assert first.status_code == 200
            context = first.json()["data"]["context"]
            assert context["through_event_sequence"].isdigit()
            assert first.json()["data"]["assessment_counts"]["all"] == "1"

            detail = await client.get(
                f"{base}/case-00",
                headers=headers,
                params={
                    "expected_result_snapshot_id": context["result_snapshot_id"],
                    "expected_label_snapshot_id": context["label_snapshot_id"],
                    "include_attempts": "true",
                    "include_response": "true",
                },
            )
            assert detail.status_code == 200
            payload = detail.json()["data"]
            assert payload["context"] == context
            assert len(payload["case_input_hash"]) == 64
            assert [item["option_id"] for item in payload["probabilities"]] == ["yes", "no"]
            assert "transport-private" not in repr(payload)

            one_sided = await client.get(
                base,
                headers=headers,
                params={"expected_result_snapshot_id": context["result_snapshot_id"]},
            )
            assert one_sided.status_code == 422
            assert (
                one_sided.json()["error"]["reason"] == "result_context_selector_pair_required"
            )

            bad_filter = await client.get(
                base, headers=headers, params={"assessment_filter": "unknown-filter"}
            )
            assert bad_filter.status_code == 422
            assert bad_filter.json()["error"]["reason"] == "invalid_request"

            duplicate = await client.get(
                f"{base}?assessment_filter=all&assessment_filter=incorrect", headers=headers
            )
            assert duplicate.status_code == 422
            assert duplicate.json()["error"]["reason"] == "invalid_query"

    asyncio.run(exercise())
    assert captures == 3
    assert not commits
