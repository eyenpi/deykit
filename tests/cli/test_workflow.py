"""Packaged walkthrough resources carry the independently authored oracle."""

import json
from importlib.resources import files


def test_packaged_workflow_has_exact_authored_numerical_inputs_and_oracles() -> None:
    resources = files("deykit.resources.cli_workflow")
    cases = resources.joinpath("cases.jsonl").read_text(encoding="utf-8")
    fixture_a = resources.joinpath("fixture-a.jsonl").read_text(encoding="utf-8")
    fixture_b = resources.joinpath("fixture-b.jsonl").read_text(encoding="utf-8")
    assert '"amount":9007199254740993' in cases
    assert '"ratio":0.1234567890123456789' in cases
    assert '"amount":9007199254740993' in fixture_a
    assert '"ratio":0.1234567890123456789' in fixture_b

    oracle = json.loads(resources.joinpath("oracle.json").read_text(encoding="utf-8"))
    assert oracle["case_count"] == 6
    assert oracle["fixture_a"]["eligible_set_count"] == 3
    assert oracle["fixture_a"]["correct_set_count"] == 2
    assert oracle["fixture_a"]["class_f1"] == {
        "accept": [2, 3],
        "review": [0, 1],
        "macro": [1, 3],
    }
    assert oracle["fixture_a"]["baseline_accuracy"] == [2, 3]
    assert oracle["fixture_a"]["usage_unavailable"] is True
    assert oracle["fixture_a"]["latency_unavailable"] is True
    assert oracle["fixture_b"] == {"eligible_set_count": 3, "correct_set_count": 3}
    assert oracle["label_revision_comparison"] == {
        "quality_denominator": 2,
        "primary_counts": {
            "both_correct": 2,
            "changed_expectations": 1,
            "unlabelled_agreement": 1,
            "unavailable_answer": 2,
        },
    }
    assert oracle["regression_check_v1_a"] == {
        "attempts": 1,
        "expectation_failures": 1,
        "exit_code": 5,
    }
    assert oracle["regression_check_v2_b"] == {
        "attempts": 1,
        "expectation_failures": 0,
        "exit_code": 0,
    }
