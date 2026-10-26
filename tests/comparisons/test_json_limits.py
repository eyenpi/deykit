"""Comparison aggregates have their own bounds; individual inputs stay bounded."""

import pytest
from pydantic import ValidationError

from deykit.application.comparisons import comparison_hash
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import JsonDocument, JsonError, semantic_hash
from deykit.contracts.records import ComparisonRecord


def comparison(source):
    return ComparisonRecord(
        id="comparison",
        left_evaluation_id="left",
        right_evaluation_id="right",
        left_result_snapshot_id="left-result",
        right_result_snapshot_id="right-result",
        outcomes_source=source,
        content_hash="0" * 64,
        created_at="2026-10-26T00:00:00Z",
    )


def test_comparison_source_and_hash_above_user_and_generated_limits():
    source = '{"aggregate":"' + "x" * (2 * 1024 * 1024) + '"}'
    record = comparison(source)
    assert load_record(ComparisonRecord, dump_record(record)) == record
    assert len(comparison_hash(record)) == 64
    with pytest.raises(JsonError, match="json_resource_limit"):
        JsonDocument(source)


def test_small_comparison_hash_retains_original_definition():
    record = comparison('{"count":100,"exact":9007199254740993}')
    assert comparison_hash(record) == semantic_hash(
        {
            "profile": "deykit-comparison-v1",
            "left_evaluation_id": "left",
            "right_evaluation_id": "right",
            "left_result_snapshot_id": "left-result",
            "right_result_snapshot_id": "right-result",
            "outcomes": {"count": 100, "exact": 9007199254740993},
        }
    )


@pytest.mark.parametrize(
    "source",
    (
        '"' + "x" * (4 * 1024 * 1024) + '"',
        "[" + ",".join("null" for _ in range(200_000)) + "]",
        "[" * 65 + "null" + "]" * 65,
    ),
)
def test_comparison_aggregate_bounds_are_finite(source):
    with pytest.raises(ValidationError):
        comparison(source)
