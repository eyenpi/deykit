"""Frozen result browsing is case-complete and raw evidence is opt-in."""

import asyncio

from deykit.application.evaluations import EvaluationService
from deykit.application.results import ResultInspection, _sanitized_source
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DispatchOutcome, NormalizedAnswer, ResultSnapshot
from deykit.runner.planner import RunRequest


def test_list_show_filters_and_explicit_raw_evidence(setup):
    source, runner, factory, clock = setup(2, invalid=(1,))
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(question_id="q", option_id="yes", reported_model="authored-v1"),
            raw_response_source=(
                '{"answers":{"q":{"option_id":"yes"}},"Authorization":"Bearer private-token"}'
            ),
        )
    ]
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    inspection = ResultInspection(source)
    listing = inspection.list(run.run_id)
    assert listing.selected_count == 2
    assert listing.status_counts["valid"] == 1
    assert listing.status_counts["input_invalid"] == 1
    assert listing.filtered_count == 2
    assert [row.case.id for row in listing.items] == ["case-00", "case-01"]
    assert inspection.list(run.run_id, status="response_error").filtered_count == 0
    assert inspection.list(run.run_id, status="valid").items[0].case.id == "case-00"
    assert inspection.list(run.run_id, split="test").filtered_count == 0
    first = inspection.list(run.run_id, limit=1)
    second = inspection.list(run.run_id, limit=1, cursor=first.next_cursor)
    assert [item.case.id for item in (*first.items, *second.items)] == ["case-00", "case-01"]
    default = inspection.show(run.run_id, "case-00").source()
    assert default["attempts"] == [] and default["input_source"] is None
    assert "private-token" not in repr(default)
    detailed = inspection.show(
        run.run_id,
        "case-00",
        include_attempts=True,
        include_request=True,
        include_response=True,
    ).source()
    assert detailed["attempts"][0]["request_body_hash"] == factory.calls[0][1].body_hash
    assert "private-token" not in repr(detailed)
    assert "[REDACTED]" in detailed["attempts"][0]["response_source"]
    initial = min(
        (
            ResultSnapshot.model_validate_json(
                source.read(ResourceKey("result_snapshots", item)).body
            )
            for item in source.list_ids("result_snapshots")
        ),
        key=lambda item: item.through_event_sequence,
    )
    saved = EvaluationService(source, clock, lambda: "initial-evaluation").evaluate_saved(
        run.run_id, initial.id, operation_id="evaluate-initial"
    )
    old = inspection.show(
        run.run_id, "case-00", evaluation_id=saved.record.id, include_attempts=True
    ).source()
    assert old["status"] == "pending" and old["attempts"] == []


def test_pure_redactor_keeps_ids_and_hides_known_secret_fields():
    redacted = _sanitized_source(
        b'{"question":"Authorization","probabilities":{"Bearer fake":0.5},'
        b'"headers":{"api-key":"x"}}'
    )
    assert '"headers":"[REDACTED]"' in redacted
    assert "Bearer fake" not in redacted
