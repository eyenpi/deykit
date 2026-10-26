"""Real-store snapshots must agree with the exact historical dispatch boundary."""

import asyncio
from dataclasses import replace

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.evaluation_evidence import snapshot_attempts
from deykit.application.evaluations import EvaluationService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import AttemptEvent, CaseResult, ResultSnapshot, RunEvent
from deykit.runner.history import read_history
from deykit.runner.planner import RunRequest, evidence_hash


def save_snapshot(source, history, results, boundary, name):
    snapshot = ResultSnapshot(
        id=name,
        run_id=history.manifest.id,
        results=results,
        through_event_sequence=boundary,
        content_hash=evidence_hash(tuple(item.model_dump_json().encode() for item in results)),
        created_at=history.manifest.created_at,
    )
    source.commit(
        name, (SourceChange(ResourceKey("result_snapshots", name), dump_record(snapshot), None),)
    )
    return snapshot


@pytest.mark.parametrize(
    "mutation",
    ["nonexistent_attempt", "contradictory_answer", "before_dispatch", "wrong_case_attempt"],
)
def test_correct_hash_does_not_authenticate_attempt_evidence(setup, mutation):
    source, runner, _, clock = setup(2)
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    history = read_history(source, run.run_id)
    results = list(history.results())
    boundary = history.boundary
    if mutation == "nonexistent_attempt":
        results[0] = results[0].model_copy(update={"attempt_id": "does-not-exist"})
    elif mutation == "contradictory_answer":
        results[0] = results[0].model_copy(
            update={"answer": results[0].answer.model_copy(update={"option_id": "no"})}
        )
    elif mutation == "wrong_case_attempt":
        results[0] = results[0].model_copy(update={"attempt_id": results[1].attempt_id})
    else:
        boundary = next(
            item.sequence for item in history.events if item.state == "attempt_reserved"
        )
    snapshot = save_snapshot(source, history, tuple(results), boundary, "forged")
    with pytest.raises(ServiceFailure) as raised:
        EvaluationService(source, clock).evaluate_saved(
            run.run_id, snapshot.id, operation_id="evaluate"
        )
    assert raised.value.error.reason == "result_attempt_evidence_mismatch"
    assert source.list_ids("evaluations") == ()


def test_dispatched_unsettled_usage_and_later_outcome_are_historically_bounded(setup):
    source, runner, factory, clock = setup(2)
    from conftest import answer

    from deykit.providers.choice import JEV_DESTINATION

    factory.profile_value = factory.profile_value.model_copy(
        update={"adapter": "jev", "destination": JEV_DESTINATION, "requested_model": "jev-latest"}
    )

    source.commit(
        "profile",
        (
            SourceChange(
                ResourceKey("providers", "authored"), dump_record(factory.profile_value), None
            ),
        ),
    )

    captured = []
    evaluations = EvaluationService(source, clock)

    # Both calls enter before either returns. The first records usage while the
    # other remains in flight; the final run later contains both known outcomes.
    async def execute():
        entered = asyncio.Event()
        first_settled = asyncio.Event()

        async def dispatch(case_id, request):
            if case_id == "case-00":
                await entered.wait()
                return answer().model_copy(
                    update={"usage_source": '{"input_tokens":10,"output_tokens":2}'}
                )
            entered.set()
            await first_settled.wait()
            return answer().model_copy(
                update={"usage_source": '{"input_tokens":20,"output_tokens":4}'}
            )

        factory.callback = dispatch

        def progress(value):
            if any(case.status == "valid" for case in value.cases) and not captured:
                try:
                    history = read_history(source, value.run_id)
                    snapshot = save_snapshot(
                        source, history, history.results(), history.boundary, "in-flight"
                    )
                    captured.append(
                        evaluations.evaluate_saved(
                            value.run_id, snapshot.id, operation_id="evaluate-in-flight"
                        )
                    )
                finally:
                    first_settled.set()

        return await runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="live", provider_id="authored"
            ),
            operation_id="start",
            on_progress=progress,
        )

    run = asyncio.run(execute())
    history = read_history(source, run.run_id)
    boundary = next(item.sequence for item in history.events if item.state == "attempt_settled")
    assert (
        sum(
            item.state == "attempt_dispatched" and item.sequence < boundary
            for item in history.events
        )
        == 2
    )
    settled_id = next(item.attempt_id for item in history.events if item.sequence == boundary)
    unsettled = next(item for item in history.attempts if item.id != settled_id)
    results = tuple(
        result
        if result.attempt_id == settled_id
        else CaseResult(
            case_id=result.case_id,
            input_hash=result.input_hash,
            status="unknown",
            attempt_id=unsettled.id,
            error=ServiceError(code="run_incomplete", reason="unsettled_attempt"),
        )
        for result in history.results()
    )
    partial = save_snapshot(source, history, results, boundary, "partial")
    service = EvaluationService(source, clock)
    view = service.evaluate_saved(run.run_id, partial.id, operation_id="evaluate-partial")
    assert len(captured) == 1
    assert captured[0].metrics["usage"] == view.metrics["usage"]
    assert (
        evaluations.frozen_context(
            run.run_id, captured[0].record.result_snapshot_id
        ).results.results
        == results
    )
    usage = view.metrics["usage"]
    assert usage["dispatched_attempt_count"] == 2
    assert usage["reported_attempt_count"] == 1
    assert usage["reported_input_tokens"] == 10
    assert usage["reported_output_tokens"] == 2
    assert usage["total_input_tokens"] is None and usage["total_output_tokens"] is None
    assert usage["reason"] == "partial_reported_usage"
    assert view.metrics["summary"]["status_counts"]["unknown"] == 1
    final = service.evaluate_saved(
        run.run_id, run.latest_result_snapshot_id, operation_id="evaluate-final"
    )
    assert final.metrics["usage"]["total_input_tokens"] == 30
    assert service.read(view.record.id).metrics == view.metrics
    assert len(factory.calls) == 2


def test_captured_history_has_same_validation_and_no_source_reads(setup):
    from deykit.runner.history import history_from_records

    source, runner, _, _ = setup(1)
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    captured = source.capture_snapshot()
    assert history_from_records(captured, run.run_id) == read_history(source, run.run_id)
    bad = tuple(
        replace(item, body=item.body.replace(b'"number":1', b'"number":2'))
        if item.key.collection == "attempts"
        else item
        for item in captured
    )
    with pytest.raises(ServiceFailure) as raised:
        history_from_records(bad, run.run_id)
    assert raised.value.error.reason == "invalid_run_sequence"


@pytest.mark.parametrize("mutation", ["foreign_attempt_event", "future_marker"])
def test_historical_snapshot_rejects_malformed_future_evidence(setup, mutation):
    source, runner, _, _ = setup(2)
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    history = read_history(source, run.run_id)
    snapshot = save_snapshot(
        source,
        history,
        tuple(
            CaseResult(case_id=item.case_id, input_hash=item.input_hash, status="pending")
            for item in history.prepared
        ),
        0,
        "before-dispatch",
    )
    records = source.capture_snapshot()
    assert snapshot_attempts(records, snapshot) == ()
    if mutation == "foreign_attempt_event":
        selected = next(item for item in records if item.key.collection == "attempt_events")
        event = load_record(AttemptEvent, selected.body)
        changed = event.model_copy(update={"attempt_id": "foreign-attempt"})
    else:
        selected = next(
            item
            for item in records
            if item.key.collection == "run_events"
            and load_record(RunEvent, item.body).state == "attempt_settled"
        )
        event = load_record(RunEvent, selected.body)
        assert event.sequence > snapshot.through_event_sequence
        changed = event.model_copy(update={"state": "attempt_dispatched"})
    body = dump_record(changed)
    malformed = tuple(
        replace(item, body=body, etag=bytes_hash(body)) if item.key == selected.key else item
        for item in records
    )
    with pytest.raises(ServiceFailure) as rejected:
        snapshot_attempts(malformed, snapshot)
    assert rejected.value.error.reason == "attempt_marker_mismatch"
