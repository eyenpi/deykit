"""Evaluation persists only frozen runner evidence in the real project source."""

import asyncio
import itertools

from deykit.application.evaluations import EvaluationService
from deykit.application.labels import LabelService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, ResultSnapshot
from deykit.runner.planner import RunRequest


def test_evaluate_saved_run_is_immutable_and_replayable(setup):
    source, runner, factory, clock = setup(3, invalid=(2,))
    result = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    snapshots = source.list_ids("result_snapshots")
    latest = max(
        (source.read(ResourceKey("result_snapshots", item)) for item in snapshots),
        key=lambda item: ResultSnapshot.model_validate_json(item.body).through_event_sequence,
    )
    assert latest is not None
    snapshot_id = ResultSnapshot.model_validate_json(latest.body).id
    counter = itertools.count()
    service = EvaluationService(source, clock, lambda: f"evaluation-{next(counter)}")
    first = service.evaluate_saved(result.run_id, snapshot_id, operation_id="evaluate")
    assert first.metrics["summary"]["selected_count"] == 3
    assert first.metrics["summary"]["status_counts"] == {
        "pending": 0,
        "input_invalid": 1,
        "response_error": 0,
        "unknown": 0,
        "valid": 2,
    }
    assert first.metrics["summary"]["coverage"]["numerator"] == 2
    assert first.metrics["summary"]["set_accuracy"]["value"] is None
    assert first.metrics["latency"]["reason"] == "fixture_has_no_live_latency"
    assert factory.calls and len(factory.calls) == 2
    replay = service.evaluate_saved(result.run_id, snapshot_id, operation_id="evaluate")
    assert replay.record.id == first.record.id and replay.replayed
    assert len(factory.calls) == 2
    assert service.read(first.record.id).metrics == first.metrics


def test_reevaluation_freezes_current_labels_without_new_dispatch(setup):
    source, runner, factory, clock = setup(1)
    label_counter = itertools.count()
    labels = LabelService(source, clock, lambda: f"label-change-{next(label_counter)}")
    first_review = labels.read("decision", "data", "case-00").review
    labels.set(first_review, ("no",), provenance="human", operation_id="initial-label")
    result = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    snapshot_id = max(
        (
            ResultSnapshot.model_validate_json(
                source.read(ResourceKey("result_snapshots", item)).body
            )
            for item in source.list_ids("result_snapshots")
        ),
        key=lambda item: item.through_event_sequence,
    ).id
    evaluation_counter = itertools.count()
    evaluations = EvaluationService(source, clock, lambda: f"evaluation-{next(evaluation_counter)}")
    original = evaluations.evaluate_saved(result.run_id, snapshot_id, operation_id="original")
    assert original.metrics["summary"]["set_accuracy"]["value"] == "0.000000"
    updated_review = labels.read("decision", "data", "case-00").review
    labels.set(updated_review, ("yes",), provenance="human", operation_id="correct-label")
    corrected = evaluations.reevaluate_current_labels(
        result.run_id, snapshot_id, operation_id="reevaluate"
    )
    assert corrected.metrics["summary"]["set_accuracy"]["value"] == "1.000000"
    assert corrected.record.result_snapshot_id == original.record.result_snapshot_id
    assert corrected.record.label_snapshot_id != original.record.label_snapshot_id
    assert corrected.record.mode == "saved_answer_reevaluation"
    assert evaluations.read(original.record.id).metrics == original.metrics
    assert len(factory.calls) == 1
    changed_review = labels.read("decision", "data", "case-00").review
    labels.set(changed_review, ("no",), provenance="human", operation_id="change-again")
    replay = evaluations.reevaluate_current_labels(
        result.run_id, snapshot_id, operation_id="reevaluate"
    )
    assert replay.replayed and replay.record.id == corrected.record.id
    assert replay.metrics == corrected.metrics and len(factory.calls) == 1
    case_key = ResourceKey("cases", "case-00", ("data",))
    stored_case = source.read(case_key)
    assert stored_case is not None
    case = load_record(CaseRecord, stored_case.body)
    edited = CaseRecord(
        id=case.id,
        dataset_id=case.dataset_id,
        input_kind="json",
        input_source='{"text":"edited after run"}',
    )
    source.commit(
        "edit-input",
        (SourceChange(case_key, dump_record(edited), stored_case.etag),),
    )
    new_review = labels.read("decision", "data", "case-00").review
    labels.set(new_review, ("yes",), provenance="human", operation_id="label-for-new-input")
    stale = evaluations.reevaluate_current_labels(
        result.run_id, snapshot_id, operation_id="stale-input-reevaluation"
    )
    assert stale.metrics["summary"]["set_accuracy"]["value"] is None
    assert stale.metrics["summary"]["exclusion_counts"]["stale"] == 1
    assert evaluations.read(corrected.record.id).metrics == corrected.metrics
    assert len(factory.calls) == 1


def test_partial_evaluation_remains_old_after_resume(setup):
    source, runner, factory, clock = setup(1)
    initial = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
            on_created=lambda created: runner.cancel(created.run_id, operation_id="cancel"),
        )
    )
    snapshots = tuple(
        ResultSnapshot.model_validate_json(source.read(ResourceKey("result_snapshots", item)).body)
        for item in source.list_ids("result_snapshots")
    )
    partial = max(snapshots, key=lambda item: item.through_event_sequence)
    assert partial.results[0].status == "pending" and factory.calls == []
    counter = itertools.count()
    evaluations = EvaluationService(source, clock, lambda: f"evaluation-{next(counter)}")
    old = evaluations.evaluate_saved(initial.run_id, partial.id, operation_id="old")
    assert old.metrics["summary"]["coverage"]["numerator"] == 0
    asyncio.run(runner.resume(initial.run_id, operation_id="resume"))
    latest = max(
        (
            ResultSnapshot.model_validate_json(
                source.read(ResourceKey("result_snapshots", item)).body
            )
            for item in source.list_ids("result_snapshots")
        ),
        key=lambda item: item.through_event_sequence,
    )
    assert latest.id != partial.id and latest.results[0].status == "valid"
    fresh = evaluations.evaluate_saved(initial.run_id, latest.id, operation_id="fresh")
    assert fresh.metrics["summary"]["coverage"]["numerator"] == 1
    assert evaluations.read(old.record.id).metrics == old.metrics
    assert len(factory.calls) == 1
