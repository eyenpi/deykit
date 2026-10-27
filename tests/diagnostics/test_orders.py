"""Independent bounded expansion and original-case denominator oracles."""

import itertools

import pytest

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
from deykit.diagnostics.orders import DiagnosticInvalid, choice_orders
from deykit.diagnostics.summary import summarize_order_analysis, summarize_orders
from deykit.domain.case_identity import case_input_hash
from deykit.metrics.summary import assess_results


def definition():
    return ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Pick.",
                options=(ChoiceOption(id="A", name="Alpha"), ChoiceOption(id="B", name="Beta")),
            ),
        ),
    )


def result(case, option, *, input_hash="a" * 64):
    return CaseResult(
        case_id=case,
        input_hash=input_hash,
        status="valid" if option else "unknown",
        attempt_id="attempt-" + case,
        answer=NormalizedAnswer(question_id="q", option_id=option) if option else None,
    )


@pytest.mark.parametrize("seed", [0, 1, -1, 2**63 - 1, -(2**63)])
def test_two_options_have_only_two_distinct_orders(seed):
    assert choice_orders(("A", "B"), orders=4, seed=seed) == (("A", "B"), ("B", "A"))
    assert choice_orders(("B", "A"), orders=4, seed=seed) == (("B", "A"), ("A", "B"))


def test_three_option_golden_orders_and_bounded_alternatives():
    original = ("A", "B", "C")
    assert choice_orders(original) == (original, ("B", "A", "C"), ("C", "B", "A"), ("C", "A", "B"))
    possible = set(itertools.permutations(original))
    for count in range(1, 5):
        orders = choice_orders(original, orders=count, seed=42)
        assert orders[0] == original
        assert len(orders) == len(set(orders)) == count
        assert set(orders) <= possible
        assert orders == choice_orders(original, orders=count, seed=42)
    assert choice_orders(original, seed=0) != choice_orders(original, seed=42)


@pytest.mark.parametrize(
    "options,count,seed",
    [
        (("A",), 4, 0),
        (("A", "A"), 4, 0),
        (("A", "../B"), 4, 0),
        (("A", "B"), 5, 0),
        (("A", "B"), True, 0),
        (("A", "B"), 4, False),
        (("A", "B"), 4, 2**63),
    ],
)
def test_bad_expansion_is_rejected(options, count, seed):
    with pytest.raises(DiagnosticInvalid):
        choice_orders(options, orders=count, seed=seed)


def test_grouped_denominator_counts_original_cases_and_preserves_unknown():
    by_order = (
        (result("case-1", "A"), result("case-2", "B")),
        (result("case-1", "B"), result("case-2", None)),
        (result("case-1", "A"), result("case-2", "B")),
        (result("case-1", "A"), result("case-2", "B")),
    )
    summary = summarize_orders(definition(), ("case-1", "case-2"), by_order)
    assert summary.independent_case_count == 2
    assert summary.expanded_result_count == 8
    assert summary.fully_observed_case_count == 1
    assert summary.disagreement.numerator == 1 and summary.disagreement.denominator == 2
    assert summary.disagreement.source()["value"] == "0.500000"
    assert summary.cases[0].observed_disagreement
    assert summary.cases[1].option_ids == ("B", None, "B", "B")
    assert not summary.cases[1].fully_observed
    assert not summary.cases[1].observed_disagreement


def test_one_order_does_not_establish_sensitivity():
    summary = summarize_orders(definition(), ("case",), ((result("case", "A"),),))
    assert summary.disagreement.denominator == 0 and summary.disagreement.exact is None
    assert summary.disagreement.reason == "no_comparable_cases"


@pytest.mark.parametrize(
    "mutation", ["different_input", "foreign_choice", "wrong_case", "untrusted_model"]
)
def test_incompatible_or_tampered_groups_are_rejected(mutation, capsys):
    original = result("case", "A")
    other = result("case", "B")
    if mutation == "different_input":
        other = result("case", "B", input_hash="b" * 64)
    elif mutation == "foreign_choice":
        other = other.model_copy(
            update={"answer": NormalizedAnswer(question_id="q", option_id="absent")}
        )
    elif mutation == "wrong_case":
        other = result("different", "B")
    else:
        other = other.model_copy(update={"answer": "PRIVATE_DIAGNOSTIC_SENTINEL"})
    with pytest.raises(DiagnosticInvalid) as error:
        summarize_orders(definition(), ("case",), ((original,), (other,)))
    assert "PRIVATE_DIAGNOSTIC_SENTINEL" not in str(error.value)
    assert not capsys.readouterr().err


def test_accuracy_gap_and_flips_use_explicit_distinct_denominators():
    stamp = "2026-10-27T12:00:00Z"
    cases = tuple(
        CaseRecord(id=f"case-{i}", dataset_id="data", input_kind="text", input_source=f'"{i}"')
        for i in range(1, 9)
    )
    dataset = DatasetSnapshot(
        id="dataset", dataset_id="data", cases=cases, content_hash="0" * 64, created_at=stamp
    )
    expected = {1: ("A",), 2: ("B",), 3: ("A", "B"), 4: ("A",), 6: ("B",), 7: ("A",), 8: ("B",)}
    labels = LabelSnapshot(
        id="labels",
        decision_id="decision",
        dataset_snapshot_id=dataset.id,
        labels=tuple(
            LabelRecord(
                id=f"label-{i}",
                decision_id="decision",
                dataset_id="data",
                case_id=case.id,
                question_id="q",
                input_hash="0" * 64 if i == 7 else case_input_hash(case),
                acceptable_option_ids=expected[i],
                status="disputed" if i == 6 else "active",
                provenance=(
                    "model_generated"
                    if i == 2
                    else "imported_unknown"
                    if i == 3
                    else "authored_fixture"
                ),
                updated_at=stamp,
            )
            for i, case in enumerate(cases, 1)
            if i in expected
        ),
        content_hash="0" * 64,
        created_at=stamp,
    )
    answers = (
        ("A", "B", "A", "A", "A", "B", "A", None),
        ("B", "B", "A", None, "B", "B", "B", "A"),
        ("A", "A", "B", "B", "A", "B", "A", "A"),
    )
    results_by_order = tuple(
        tuple(
            result(case.id, answer, input_hash=case_input_hash(case))
            for case, answer in zip(cases, order, strict=True)
        )
        for order in answers
    )
    assessments = tuple(
        assess_results(
            definition(),
            dataset,
            labels,
            ResultSnapshot(
                id=f"results-{i}",
                run_id=f"run-{i}",
                results=results,
                through_event_sequence=0,
                content_hash="0" * 64,
                created_at=stamp,
            ),
            tuple(case.id for case in cases),
        ).cases
        for i, results in enumerate(results_by_order)
    )
    summary = summarize_orders(definition(), tuple(case.id for case in cases), results_by_order)
    analysis = summarize_order_analysis(summary, assessments, (("A", "B"), ("B", "A"), ("A", "B")))
    assert [item.option_order for item in analysis.orders] == [
        ("A", "B"),
        ("B", "A"),
        ("A", "B"),
    ]

    assert [(item.accuracy.numerator, item.accuracy.denominator) for item in analysis.orders] == [
        (4, 4),
        (2, 4),
        (2, 5),
    ]
    assert [
        (item.common_accuracy.numerator, item.common_accuracy.denominator)
        for item in analysis.orders
    ] == [(3, 3), (2, 3), (2, 3)]
    assert (analysis.accuracy_gap.numerator, analysis.accuracy_gap.denominator) == (3, 5)
    assert (analysis.common_accuracy_gap.numerator, analysis.common_accuracy_gap.denominator) == (
        1,
        3,
    )
    assert analysis.orders[0].accuracy_label_provenance == (
        ("authored_fixture", 2),
        ("imported_unknown", 1),
        ("model_generated", 1),
    )
    assert analysis.orders[1].accuracy_exclusions == (
        ("disputed", 1),
        ("no_valid_answer", 1),
        ("stale", 1),
        ("unlabelled", 1),
    )
    assert analysis.orders[0].flips_from_original.reason == "original_order"
    assert [
        (item.flips_from_original.numerator, item.flips_from_original.denominator)
        for item in analysis.orders[1:]
    ] == [(3, 6), (3, 7)]
    assert analysis.cases[3].flipped_from_original == (None, None, True)
    assert (analysis.cases[3].flip_rate.numerator, analysis.cases[3].flip_rate.denominator) == (
        1,
        1,
    )
    assert analysis.cases[7].flip_rate.reason == "no_comparable_orders"


def test_order_analysis_reports_unavailable_accuracy_and_gap():
    stamp = "2026-10-27T12:00:00Z"
    case = CaseRecord(id="case", dataset_id="data", input_kind="text", input_source='"x"')
    dataset = DatasetSnapshot(
        id="dataset", dataset_id="data", cases=(case,), content_hash="0" * 64, created_at=stamp
    )
    labels = LabelSnapshot(
        id="labels",
        decision_id="decision",
        dataset_snapshot_id=dataset.id,
        labels=(),
        content_hash="0" * 64,
        created_at=stamp,
    )
    answer = result(case.id, "A", input_hash=case_input_hash(case))
    results = ResultSnapshot(
        id="results",
        run_id="run",
        results=(answer,),
        through_event_sequence=0,
        content_hash="0" * 64,
        created_at=stamp,
    )
    assessment = assess_results(definition(), dataset, labels, results, (case.id,))
    summary = summarize_orders(definition(), (case.id,), ((answer,),))
    analysis = summarize_order_analysis(summary, (assessment.cases,), (("A", "B"),))
    assert analysis.orders[0].accuracy.reason == "no_eligible_labels"
    assert analysis.orders[0].common_accuracy.reason == "no_comparable_labeled_cases"
    assert analysis.accuracy_gap.reason == "fewer_than_two_orders"
    assert analysis.common_accuracy_gap.reason == "fewer_than_two_orders"
    assert analysis.cases[0].flip_rate.reason == "no_comparable_orders"

    two_orders = summarize_orders(definition(), (case.id,), ((answer,), (answer,)))
    unavailable = summarize_order_analysis(
        two_orders, (assessment.cases, assessment.cases), (("A", "B"), ("B", "A"))
    )
    assert unavailable.accuracy_gap.reason == "order_accuracy_unavailable"
    assert unavailable.common_accuracy_gap.reason == "no_comparable_labeled_cases"


def test_admitted_diagnostic_assessments_handle_large_case_and_option_sets():
    from deykit.metrics.summary import assess_admitted_cases

    stamp = "2026-10-27T12:00:00Z"
    cases = tuple(
        CaseRecord(id=f"case-{i:04}", dataset_id="data", input_kind="text", input_source='"x"')
        for i in range(4_000)
    )
    dataset = DatasetSnapshot(
        id="dataset", dataset_id="data", cases=cases, content_hash="0" * 64, created_at=stamp
    )
    labels = LabelSnapshot(
        id="labels",
        decision_id="decision",
        dataset_snapshot_id=dataset.id,
        labels=(),
        content_hash="0" * 64,
        created_at=stamp,
    )
    answers = tuple(result(case.id, None, input_hash=case_input_hash(case)) for case in cases)
    results = ResultSnapshot(
        id="results",
        run_id="run",
        results=answers,
        through_event_sequence=0,
        content_hash="0" * 64,
        created_at=stamp,
    )
    wide_definition = ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Pick.",
                options=tuple(
                    ChoiceOption(id=f"option-{i}", name=f"Option {i}") for i in range(10_000)
                ),
            ),
        ),
    )
    assessed = assess_admitted_cases(
        wide_definition, dataset, labels, results, tuple(case.id for case in cases)
    )
    assert len(assessed) == 4_000
    assert all(
        case.set_correct is None and case.exclusion_reasons == ("no_valid_answer", "unlabelled")
        for case in assessed
    )


def test_admitted_diagnostic_assessments_handle_many_labeled_valid_answers():
    from deykit.metrics.summary import assess_admitted_cases

    stamp = "2026-10-27T12:00:00Z"
    cases = tuple(
        CaseRecord(id=f"case-{i:04}", dataset_id="data", input_kind="text", input_source='"x"')
        for i in range(4_000)
    )
    dataset = DatasetSnapshot(
        id="dataset", dataset_id="data", cases=cases, content_hash="0" * 64, created_at=stamp
    )
    labels = LabelSnapshot(
        id="labels",
        decision_id="decision",
        dataset_snapshot_id=dataset.id,
        labels=tuple(
            LabelRecord(
                id=f"label-{i}",
                decision_id="decision",
                dataset_id="data",
                case_id=case.id,
                question_id="q",
                input_hash=case_input_hash(case),
                acceptable_option_ids=("A",),
                provenance="authored_fixture",
                updated_at=stamp,
            )
            for i, case in enumerate(cases)
        ),
        content_hash="0" * 64,
        created_at=stamp,
    )
    answers = tuple(result(case.id, "A", input_hash=case_input_hash(case)) for case in cases)
    results = ResultSnapshot(
        id="results",
        run_id="run",
        results=answers,
        through_event_sequence=0,
        content_hash="0" * 64,
        created_at=stamp,
    )
    assessed = assess_admitted_cases(
        definition(), dataset, labels, results, tuple(case.id for case in cases)
    )
    assert len(assessed) == 4_000
    assert all(
        case.set_correct is True and case.label_provenance == "authored_fixture"
        for case in assessed
    )
