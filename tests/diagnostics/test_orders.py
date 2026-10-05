"""Independent bounded expansion and original-case denominator oracles."""

import itertools

import pytest

from deykit.contracts.records import (
    CaseResult,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    NormalizedAnswer,
)
from deykit.diagnostics.orders import DiagnosticInvalid, choice_orders
from deykit.diagnostics.summary import summarize_orders


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
