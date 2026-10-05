"""Independent arithmetic oracle for authored examples; no runner or provider calls."""

from fractions import Fraction

import pytest

from deykit.contracts.json_value import JsonDocument
from deykit.contracts.records import (
    CaseRecord,
    CaseResult,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetSnapshot,
    LabelRecord,
    LabelSnapshot,
    NormalizedAnswer,
    ResultSnapshot,
)
from deykit.metrics.summary import MetricsInvalid, assess_results

STAMP = "2026-10-05T12:00:00Z"
HASH = "0" * 64
OPTIONS = ("question", "report", "request", "other")
EXPECTED = {
    "ex-001": "question",
    "ex-002": "report",
    "ex-003": "question",
    "ex-004": "report",
    "ex-005": "request",
    "ex-006": "question",
    "ex-007": "other",
    "ex-008": "request",
    "ex-012": "question",
}
RETURNED = {
    "ex-001": "question",
    "ex-002": "report",
    "ex-003": "report",
    "ex-004": "report",
    "ex-005": "request",
    "ex-006": "question",
    "ex-007": "other",
    "ex-008": "question",
    "ex-009": "question",
    "ex-010": "report",
}


def definition():
    return ChoiceDefinition(
        input_kind="json",
        input_schema_source=(
            '{"type":"object","required":["text"],"properties":'
            '{"text":{"type":"string","minLength":1}}}'
        ),
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="category",
                instructions="Categorize text",
                options=tuple(ChoiceOption(id=key, name=key.title()) for key in OPTIONS),
            ),
        ),
    )


def case(number, *, split="development"):
    key = f"ex-{number:03d}"
    return CaseRecord(
        id=key,
        dataset_id="examples",
        input_kind="json",
        input_source="{}" if number == 11 else '{"text":"' + key + '"}',
        split=split,
    )


def label(record, option, *, question_id="category", status="active", input_hash=None):
    return LabelRecord(
        id="label-" + record.id + "-" + question_id,
        decision_id="decision",
        dataset_id="examples",
        case_id=record.id,
        question_id=question_id,
        input_hash=input_hash or JsonDocument(record.input_source).content_hash,
        acceptable_option_ids=(option,) if isinstance(option, str) else option,
        status=status,
        provenance="authored_fixture",
        updated_at=STAMP,
    )


def frozen(cases, labels, results):
    dataset = DatasetSnapshot(
        id="dataset-snapshot",
        dataset_id="examples",
        cases=tuple(cases),
        content_hash=HASH,
        created_at=STAMP,
    )
    expectations = LabelSnapshot(
        id="label-snapshot",
        decision_id="decision",
        dataset_snapshot_id=dataset.id,
        labels=tuple(labels),
        content_hash=HASH,
        created_at=STAMP,
    )
    answers = ResultSnapshot(
        id="result-snapshot",
        run_id="run",
        results=tuple(results),
        through_event_sequence=12,
        content_hash=HASH,
        created_at=STAMP,
    )
    return dataset, expectations, answers


def result(record, option=None, *, status="valid"):
    return CaseResult(
        case_id=record.id,
        input_hash=JsonDocument(record.input_source).content_hash,
        status=status,
        attempt_id=None if status == "input_invalid" else "attempt-" + record.id,
        answer=(
            NormalizedAnswer(question_id="category", option_id=option)
            if status == "valid"
            else None
        ),
    )


def test_authored_12_case_matrix_and_exact_macro_f1():
    cases = tuple(case(number) for number in range(1, 13))
    labels = tuple(label(item, EXPECTED[item.id]) for item in cases if item.id in EXPECTED)
    results = tuple(
        result(
            item,
            RETURNED.get(item.id),
            status="input_invalid"
            if item.id == "ex-011"
            else "response_error"
            if item.id == "ex-012"
            else "valid",
        )
        for item in cases
    )
    dataset, expectations, answers = frozen(cases, labels, results)
    summary = assess_results(
        definition(), dataset, expectations, answers, tuple(c.id for c in cases)
    )
    assert summary.selected_count == 12
    assert dict(summary.status_counts) == {
        "pending": 0,
        "input_invalid": 1,
        "response_error": 1,
        "unknown": 0,
        "valid": 10,
    }
    assert summary.coverage.exact == Fraction(10, 12)
    assert (summary.eligible_set_count, summary.correct_set_count) == (8, 6)
    assert summary.set_accuracy.exact == Fraction(6, 8)
    assert summary.unlabelled_valid_count == 2
    assert summary.single_label_count == 8
    assert summary.option_ids == OPTIONS
    assert summary.confusion_matrix == (
        (2, 1, 0, 0),
        (0, 2, 0, 0),
        (1, 0, 1, 0),
        (0, 0, 0, 1),
    )
    assert tuple(item.f1.exact for item in summary.classes) == (
        Fraction(2, 3),
        Fraction(4, 5),
        Fraction(2, 3),
        Fraction(1, 1),
    )
    assert summary.macro_f1.exact == Fraction(47, 60)
    assert summary.macro_f1_class_count == 4
    assert summary.native_confidence_present_count == 0
    assert summary.native_confidence_mean.source()["value"] is None
    assert summary.native_confidence_mean.reason == "native_confidence_unavailable"
    assert summary.source()["set_accuracy"]["value"] == "0.750000"
    assert [item.case_id for item in summary.cases if item.set_correct is False] == [
        "ex-003",
        "ex-008",
    ]


def test_no_labels_invalid_answers_and_acceptable_sets_have_explicit_nulls():
    one, two = case(1), case(2)
    dataset, labels, answers = frozen(
        (one, two), (), (result(one, "question"), result(two, "report"))
    )
    unlabelled = assess_results(definition(), dataset, labels, answers, (one.id, two.id))
    assert unlabelled.coverage.exact == Fraction(1, 1)
    assert unlabelled.set_accuracy.exact is None
    assert unlabelled.set_accuracy.reason == "no_eligible_labels"
    assert unlabelled.macro_f1.exact is None
    assert unlabelled.macro_f1.reason == "no_class_evidence"
    assert unlabelled.unlabelled_valid_count == 2

    dataset, labels, answers = frozen(
        (one, two),
        (label(one, "question"), label(two, "report")),
        (result(one, status="response_error"), result(two, status="response_error")),
    )
    invalid = assess_results(definition(), dataset, labels, answers, (one.id, two.id))
    assert invalid.coverage.exact == Fraction(0, 1)
    assert invalid.coverage.reason is None
    assert invalid.set_accuracy.exact is None
    assert dict(invalid.exclusion_counts)["no_valid_answer"] == 2

    dataset, labels, answers = frozen(
        (one,), (label(one, ("question", "report")),), (result(one, "question"),)
    )
    set_only = assess_results(definition(), dataset, labels, answers, (one.id,))
    assert set_only.set_accuracy.exact == Fraction(1, 1)
    assert set_only.single_label_count == 0
    assert set_only.macro_f1.exact is None
    assert set_only.cases[0].set_correct is True
    assert set_only.cases[0].exclusion_reasons == ("acceptable_set_excluded_from_class_metrics",)


def test_combined_exclusion_causes_and_legacy_question_are_visible():
    one, two = case(1), case(2)
    disputed = label(one, "deleted", status="disputed", input_hash=HASH)
    old_question = label(two, "report", question_id="retired")
    dataset, labels, answers = frozen(
        (one, two), (disputed, old_question), (result(one, "question"), result(two, "report"))
    )
    summary = assess_results(definition(), dataset, labels, answers, (one.id, two.id))
    assert summary.cases[0].exclusion_reasons == ("disputed", "stale", "incompatible")
    assert summary.cases[0].expected_option_ids == ("deleted",)
    assert summary.cases[1].exclusion_reasons == ("incompatible_question_label",)
    assert summary.cases[1].legacy_question_ids == ("retired",)
    assert summary.cases[1].legacy_expected_option_ids == (("report",),)
    assert summary.unlabelled_valid_count == 0

    current = label(two, "report")
    dataset, labels, answers = frozen(
        (one, two),
        (disputed, old_question, current),
        (result(one, "question"), result(two, "report")),
    )
    with_current = assess_results(definition(), dataset, labels, answers, (one.id, two.id))
    assert with_current.cases[1].legacy_question_ids == ("retired",)
    assert with_current.cases[1].set_correct is True
    assert with_current.eligible_set_count == 1


def test_mismatched_frozen_identities_do_not_shrink_denominators():
    one, two = case(1), case(2)
    dataset, labels, answers = frozen((one, two), (), (result(one, "question"),))
    with pytest.raises(MetricsInvalid, match="selected_results_mismatch"):
        assess_results(definition(), dataset, labels, answers, (one.id, two.id))
    bad = label(one, "question").model_copy(update={"dataset_id": "other"})
    dataset, labels, answers = frozen((one,), (bad,), (result(one, "question"),))
    with pytest.raises(MetricsInvalid, match="frozen_label_context_mismatch"):
        assess_results(definition(), dataset, labels, answers, (one.id,))
