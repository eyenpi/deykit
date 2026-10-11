"""Independent checks for frozen result filters, pins and probability display."""

import asyncio

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.labels import LabelService
from deykit.application.results import ResultInspection
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DispatchOutcome, NormalizedAnswer, ResultSnapshot
from deykit.runner.planner import RunRequest


def _request():
    return RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )


def test_assessment_filter_counts_are_global_and_paired_pins_reject_drift(setup, monkeypatch):
    source, runner, factory, clock = setup(4, invalid=(3,))
    labels = LabelService(source, clock, lambda: "label-change")
    review = labels.read("decision", "data", "case-00").review
    labels.set(review, ("yes",), provenance="human", operation_id="label-case-00")
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            answer=NormalizedAnswer(question_id="q", option_id="no", reported_model="authored-v1"),
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
    assert inspection.list(
        run.run_id,
        assessment_filter="all",
        expected_result_snapshot_id=first.result_snapshot_id,
        expected_label_snapshot_id=first.label_snapshot_id,
        limit=1,
    ).context == first.context
    assert calls == 2

    with pytest.raises(ServiceFailure) as one_sided:
        inspection.list(run.run_id, expected_result_snapshot_id=first.result_snapshot_id)
    assert one_sided.value.error.reason == "result_context_selector_pair_required"
    with pytest.raises(ServiceFailure) as invalid_filter:
        inspection.list(run.run_id, assessment_filter="everything")
    assert invalid_filter.value.error.reason == "invalid_assessment_filter"

    latest = max(
        (
            ResultSnapshot.model_validate_json(source.read(ResourceKey("result_snapshots", key)).body)
            for key in source.list_ids("result_snapshots")
        ),
        key=lambda item: item.through_event_sequence,
    )
    saved = EvaluationService(source, clock, lambda: "saved-evaluation").evaluate_saved(
        run.run_id, latest.id, operation_id="save-evaluation"
    )
    asyncio.run(runner.resume(run.run_id, operation_id="resume", retry_unknown=True))
    with pytest.raises(ServiceFailure) as drift:
        inspection.list(
            run.run_id,
            expected_result_snapshot_id=first.result_snapshot_id,
            expected_label_snapshot_id=first.label_snapshot_id,
        )
    assert drift.value.error.reason == "result_context_changed"
    saved_page = inspection.list(run.run_id, evaluation_id=saved.record.id)
    assert saved_page.result_snapshot_id == latest.id
    assert saved_page.label_snapshot_id == saved.record.label_snapshot_id


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
