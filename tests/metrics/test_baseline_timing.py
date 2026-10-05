"""Frozen development fitting and fresh-live nearest-rank timing oracles."""

from decimal import Decimal
from fractions import Fraction

import pytest

from deykit.contracts.json_value import JsonDocument
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetSnapshot,
    LabelRecord,
    LabelSnapshot,
)
from deykit.metrics.baseline import majority_baseline
from deykit.metrics.summary import MetricsInvalid
from deykit.metrics.timing import live_latency

STAMP = "2026-10-05T12:00:00Z"
HASH = "0" * 64


def definition():
    return ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="choice",
                instructions="Choose A or B",
                options=(ChoiceOption(id="A", name="A"), ChoiceOption(id="B", name="B")),
            ),
        ),
    )


def case(key, split):
    return CaseRecord(
        id=key,
        dataset_id="dataset",
        input_kind="json",
        input_source='{"text":"' + key + '"}',
        split=split,
    )


def label(record, option, *, status="active"):
    return LabelRecord(
        id="label-" + record.id,
        decision_id="decision",
        dataset_id="dataset",
        case_id=record.id,
        question_id="choice",
        input_hash=JsonDocument(record.input_source).content_hash,
        acceptable_option_ids=(option,) if isinstance(option, str) else option,
        status=status,
        provenance="human",
        updated_at=STAMP,
    )


def frozen(dataset_id, label_id, cases, labels):
    data = DatasetSnapshot(
        id=dataset_id,
        dataset_id="dataset",
        cases=tuple(cases),
        content_hash=HASH,
        created_at=STAMP,
    )
    expected = LabelSnapshot(
        id=label_id,
        decision_id="decision",
        dataset_snapshot_id=dataset_id,
        labels=tuple(labels),
        content_hash=HASH,
        created_at=STAMP,
    )
    return data, expected


def test_majority_uses_full_frozen_development_source_and_ties_by_option_order():
    development = tuple(case(f"dev-{i}", "development") for i in range(1, 5))
    evaluation = (case("test-a", "test"), case("test-b", "test"))
    full_data, full_labels = frozen(
        "full-development",
        "full-labels",
        development + evaluation,
        tuple(
            label(record, option)
            for record, option in zip(development, ("A", "A", "B", "B"), strict=True)
        )
        + (label(evaluation[0], "A"), label(evaluation[1], "B")),
    )
    selected_data, selected_labels = frozen(
        "selected-test",
        "selected-labels",
        evaluation,
        (label(evaluation[0], "A"), label(evaluation[1], "B")),
    )
    baseline = majority_baseline(
        definition(),
        full_data,
        full_labels,
        selected_data,
        selected_labels,
        ("test-a", "test-b"),
        ("test-a", "test-b"),
    )
    assert baseline.option_id == "A"
    assert baseline.fit_support == 4
    assert baseline.fit_dataset_snapshot_id == "full-development"
    assert baseline.fit_label_snapshot_id == "full-labels"
    assert baseline.evaluation_splits == ("test",)
    assert baseline.overlap_case_ids == ()
    assert baseline.accuracy.exact == Fraction(1, 2)

    overlap_data, overlap_labels = frozen(
        "selected-development",
        "selected-development-labels",
        (development[0],),
        (label(development[0], "A"),),
    )
    overlap = majority_baseline(
        definition(),
        full_data,
        full_labels,
        overlap_data,
        overlap_labels,
        (development[0].id,),
        (development[0].id,),
    )
    assert overlap.overlap_case_ids == (development[0].id,)
    assert overlap.evaluation_splits == ("development",)


def test_baseline_unavailable_when_no_eligible_fit_labels_and_never_uses_test_labels():
    development = case("dev", "development")
    evaluation = case("test", "test")
    full_data, full_labels = frozen(
        "full",
        "full-labels",
        (development, evaluation),
        (label(development, ("A", "B")), label(evaluation, "B")),
    )
    selected_data, selected_labels = frozen(
        "selected", "selected-labels", (evaluation,), (label(evaluation, "B"),)
    )
    unavailable = majority_baseline(
        definition(), full_data, full_labels, selected_data, selected_labels, ("test",), ("test",)
    )
    assert unavailable.option_id is None
    assert unavailable.fit_support == 0
    assert unavailable.fit_excluded_acceptable_sets == 1
    assert unavailable.accuracy.exact is None
    assert unavailable.unavailable_reason == "no_eligible_development_labels"

    empty_evaluation_labels = LabelSnapshot(
        id="empty-evaluation-labels",
        decision_id="decision",
        dataset_snapshot_id=selected_data.id,
        labels=(),
        content_hash=HASH,
        created_at=STAMP,
    )
    with pytest.raises(MetricsInvalid, match="baseline_pairing_mismatch"):
        majority_baseline(
            definition(),
            full_data,
            full_labels,
            selected_data,
            empty_evaluation_labels,
            ("test",),
            ("test",),
        )


def test_paired_baseline_scores_acceptable_sets_but_does_not_fit_from_them():
    development = (case("dev-a", "development"), case("dev-set", "development"))
    evaluation = case("test-set", "test")
    full_data, full_labels = frozen(
        "full",
        "full-labels",
        development + (evaluation,),
        (
            label(development[0], "A"),
            label(development[1], ("A", "B")),
            label(evaluation, ("A", "B")),
        ),
    )
    selected_data, selected_labels = frozen(
        "selected", "selected-labels", (evaluation,), (label(evaluation, ("A", "B")),)
    )
    baseline = majority_baseline(
        definition(),
        full_data,
        full_labels,
        selected_data,
        selected_labels,
        (evaluation.id,),
        (evaluation.id,),
    )
    assert baseline.option_id == "A"
    assert baseline.fit_support == 1
    assert baseline.fit_excluded_acceptable_sets == 1
    assert (baseline.selected_count, baseline.paired_count, baseline.scored_count) == (1, 1, 1)
    assert baseline.accuracy.exact == Fraction(1, 1)


def test_live_nearest_rank_is_fresh_call_only_and_fixture_is_undefined():
    live = live_latency(
        "live", (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5"))
    )
    assert (live.sample_count, live.p50_seconds, live.p95_seconds) == (5, "3", "5")
    assert live.reason is None
    fixture = live_latency("fixture", (Decimal("1"), Decimal("2")))
    assert (fixture.sample_count, fixture.p50_seconds, fixture.p95_seconds) == (0, None, None)
    assert fixture.reason == "fixture_has_no_live_latency"
    absent = live_latency("live", ())
    assert absent.sample_count == 0 and absent.p50_seconds is None
    assert absent.reason == "no_recorded_live_durations"
    with pytest.raises(MetricsInvalid, match="invalid_latency_source"):
        live_latency("live", (True,))
    with pytest.raises(MetricsInvalid, match="invalid_latency_source"):
        live_latency("live", (float("inf"),))
