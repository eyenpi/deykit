"""Exact API display projections keep arbitrary numeric metrics out of JSON numbers."""

from decimal import Decimal

import pytest

from deykit.api.projections import exact_display_tree, service_error
from deykit.api.routes.results import _evaluation
from deykit.application.evaluations import EvaluationView
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import EvaluationRecord


def test_metric_projection_recursively_textualizes_exact_numeric_leaves() -> None:
    source = {
        "large_integer": 9_007_199_254_740_993,
        "fraction": Decimal("0.12345678901234567890123456789"),
        "flags": [True, None, {"count": 4}],
    }

    assert exact_display_tree(source) == {
        "large_integer": "9007199254740993",
        "fraction": "0.12345678901234567890123456789",
        "flags": [True, None, {"count": "4"}],
    }


def test_metric_projection_rejects_binary_float_leaves() -> None:
    with pytest.raises(TypeError, match="unsupported_projection_value"):
        exact_display_tree({"metric": 0.1})


def test_service_error_projection_bounds_rows_and_keeps_safe_identity() -> None:
    projected = service_error(
        ServiceError(
            code="run_incomplete",
            resource_id="run-1",
            reason="group_acknowledgement_incomplete",
            row=9_007_199_254_740_992,
        )
    )

    assert projected is not None
    assert projected.resource_id == "run-1"
    assert projected.reason == "group_acknowledgement_incomplete"
    assert projected.row is None


def test_evaluation_projection_preserves_admitted_metrics_source_and_exact_display() -> None:
    metrics_source = '{"macro_f1":0.875,"cases":9007199254740993}'
    record = EvaluationRecord(
        id="evaluation",
        run_id="run",
        result_snapshot_id="results",
        label_snapshot_id="labels",
        mode="original",
        metrics_source=metrics_source,
        content_hash="a" * 64,
        created_at="2026-10-09T12:00:00Z",
    )

    projected = _evaluation(
        EvaluationView(
            record,
            "b" * 64,
            {"macro_f1": Decimal("0.875"), "cases": 9_007_199_254_740_993},
        )
    )

    assert projected.metrics_source == metrics_source
    assert projected.metrics == {"macro_f1": "0.875", "cases": "9007199254740993"}
