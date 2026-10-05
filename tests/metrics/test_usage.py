"""Only explicit native usage is aggregated; unknown totals stay undefined."""

import pytest

from deykit.metrics.summary import MetricsInvalid
from deykit.metrics.usage import reported_usage


def test_fixture_does_not_inherit_provider_usage_or_pricing():
    value = reported_usage("fixture", (None,))
    assert value.source() == {
        "mode": "fixture",
        "dispatched_attempt_count": 0,
        "reported_attempt_count": 0,
        "reported_input_tokens": None,
        "reported_output_tokens": None,
        "total_input_tokens": None,
        "total_output_tokens": None,
        "source_kind": None,
        "reported_at": None,
        "reason": "fixture_no_usage",
        "cost": None,
        "cost_reason": "pricing_source_unavailable",
    }


def test_live_partial_and_complete_reported_usage():
    one = '{"input_tokens":12,"output_tokens":3}'
    two = '{"input_tokens":5,"output_tokens":7}'
    partial = reported_usage("live", (one, None), reported_at="2026-10-05T00:00:00Z")
    assert partial.reported_attempt_count == 1
    assert partial.reported_input_tokens == 12
    assert partial.total_input_tokens is None and partial.total_output_tokens is None
    assert partial.source()["reason"] == "partial_reported_usage"
    full = reported_usage("live", (one, two))
    assert (full.total_input_tokens, full.total_output_tokens) == (17, 10)
    assert full.source()["cost"] is None


@pytest.mark.parametrize(
    "source",
    [
        '{"input_tokens":true,"output_tokens":1}',
        '{"input_tokens":1.5,"output_tokens":1}',
        '{"input_tokens":-1,"output_tokens":1}',
        '{"input_tokens":1,"output_tokens":null}',
        '{"input_tokens":1,"input_tokens":2,"output_tokens":1}',
    ],
)
def test_malformed_reported_usage_is_rejected(source):
    with pytest.raises(MetricsInvalid):
        reported_usage("live", (source,))
