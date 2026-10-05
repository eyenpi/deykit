"""Independent bucket and denominator oracles over authored pure values."""

import pytest

from deykit.comparisons.models import ComparisonCaseSide, ComparisonContext, ComparisonOutcomes
from deykit.comparisons.pairing import pair_cases
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import JsonError, dump_json, parse_json
from deykit.contracts.model_admission import ModelInvalid


def context(ids, **changes):
    values = dict(
        evaluation_id="eval",
        evaluation_hash="1" * 64,
        evaluation_mode="original",
        run_id="run",
        decision_id="decision",
        dataset_id="dataset",
        decision_revision_id="rev",
        definition_hash="2" * 64,
        dataset_snapshot_id="data",
        dataset_hash="3" * 64,
        label_snapshot_id="labels",
        label_hash="4" * 64,
        result_snapshot_id="results",
        result_hash="5" * 64,
        evidence_mode="fixture",
        adapter="fixture",
        compiler_version="1",
        compiler_ids=("jev-choice",),
        requested_model="authored-test",
        answering_models=("authored-test",),
        provider_profile_id="fixture",
        provider_config_hash="6" * 64,
        question_id="q",
        option_ids=("yes", "no"),
        option_order=("yes", "no"),
        selected_case_ids=tuple(ids),
    )
    return ComparisonContext(**{**values, **changes})


def side(answer="yes", expected=("yes",), correct=True, **changes):
    values = dict(
        input_hash="a" * 64,
        status="valid",
        answer_option_id=answer,
        expected_option_ids=expected,
        label_provenance="human" if expected else None,
        exclusion_reasons=(),
        correct=correct,
    )
    return ComparisonCaseSide(**{**values, **changes})


def test_union_oracle_separates_quality_unlabelled_and_overlapping_exclusions():
    left = {
        "correct": side(),
        "improved": side("no", correct=False),
        "regressed": side(),
        "wrong": side("no", correct=False),
        "left-only": side(),
        "changed-input": side(),
        "changed-expectation": side(),
        "unknown": side(),
        "excluded": side(correct=None, exclusion_reasons=("stale", "disputed")),
        "unlabelled-same": side(expected=(), correct=None, exclusion_reasons=("unlabelled",)),
        "unlabelled-different": side(expected=(), correct=None, exclusion_reasons=("unlabelled",)),
    }
    right = {
        "correct": side(),
        "improved": side(),
        "regressed": side("no", correct=False),
        "wrong": side("no", correct=False),
        "right-only": side(),
        "changed-input": side(input_hash="b" * 64),
        "changed-expectation": side(expected=("no",), correct=False),
        "unknown": side(
            None, correct=None, status="unknown", exclusion_reasons=("no_valid_answer",)
        ),
        "excluded": side(),
        "unlabelled-same": side(expected=(), correct=None, exclusion_reasons=("unlabelled",)),
        "unlabelled-different": side(
            "no", expected=(), correct=None, exclusion_reasons=("unlabelled",)
        ),
    }
    result = pair_cases(context(left), context(right), left, right)
    assert result.primary_counts == {
        "left_only": 1,
        "right_only": 1,
        "changed_input": 1,
        "changed_question_options": 0,
        "changed_expectations": 1,
        "unavailable_answer": 1,
        "excluded_expectation": 1,
        "unlabelled_agreement": 1,
        "unlabelled_disagreement": 1,
        "both_correct": 1,
        "improved": 1,
        "regressed": 1,
        "both_wrong": 1,
    }
    assert result.quality_denominator == 4
    assert result.left_correct_count == result.right_correct_count == 2
    assert result.unlabelled_denominator == 2 and len(result.cases) == 12
    assert result.left_exclusion_counts == {"stale": 1, "disputed": 1, "unlabelled": 2}
    assert result.right_exclusion_counts == {"no_valid_answer": 1, "unlabelled": 2}
    assert result.right_status_counts["unknown"] == 1


def test_acceptable_set_and_option_order_are_semantically_equivalent():
    left = {
        "case": side(
            expected=("yes", "no"),
            exclusion_reasons=("acceptable_set_excluded_from_class_metrics",),
        )
    }
    right = {
        "case": side(
            expected=("no", "yes"),
            exclusion_reasons=("acceptable_set_excluded_from_class_metrics",),
        )
    }
    result = pair_cases(
        context(left),
        context(
            right,
            option_ids=("no", "yes"),
            option_order=("no", "yes"),
            decision_revision_id="renamed",
            definition_hash="f" * 64,
        ),
        left,
        right,
    )
    assert result.primary_counts["both_correct"] == result.quality_denominator == 1


@pytest.mark.parametrize(
    "changes",
    [dict(question_id="renamed-question"), dict(option_ids=("yes",), option_order=("yes",))],
)
def test_changed_question_or_option_identity_has_no_quality_pair(changes):
    values = {"case": side()}
    result = pair_cases(context(values), context(values, **changes), values, values)
    assert result.primary_counts["changed_question_options"] == 1
    assert result.quality_denominator == 0


def test_no_shared_resource_context_and_untrusted_nested_values():
    values = {"case": side()}
    with pytest.raises(ValueError, match="comparison_resource_mismatch"):
        pair_cases(context(values), context(values, dataset_id="other"), values, values)
    malformed = side().model_copy(update={"correct": "true"})
    with pytest.raises(ModelInvalid, match="invalid_comparison_case"):
        pair_cases(context(values), context(values), {"case": malformed}, values)


@pytest.mark.parametrize("change", ["version", "counts", "scope", "unknown"])
def test_persisted_source_rejects_invalid_versions_counts_scope_and_fields(change):
    values = {"case": side()}
    result = pair_cases(context(values), context(values), values, values)
    raw = parse_json(dump_record(result))
    if change == "version":
        raw["schema_version"] = 2
    elif change == "counts":
        raw["quality_denominator"] = 2
    elif change == "scope":
        raw["left"]["selected_case_ids"] = []
    else:
        raw["secret"] = "unknown field"
    with pytest.raises(JsonError):
        load_record(ComparisonOutcomes, dump_json(raw))
