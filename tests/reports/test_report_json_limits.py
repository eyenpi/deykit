"""Aggregate report bounds never expand individual user JSON admission."""

import json

import pytest
from pydantic import ValidationError

from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import JsonDocument, JsonError, dump_json, parse_json
from deykit.contracts.records import NormalizedAnswer, ReportRecord
from deykit.contracts.report_json import REPORT_CONTENT_LIMITS


def report(source):
    return ReportRecord(
        id="bounded-report",
        evaluation_ids=(),
        result_snapshot_ids=(),
        label_snapshot_ids=(),
        content_source=source,
        content_hash="0" * 64,
        created_at="2026-10-21T00:00:00Z",
    )


def test_aggregate_source_and_record_roundtrip_above_default_limits():
    value = {"owned_aggregate": "x" * (2 * 1024 * 1024)}
    source = json.dumps(value, separators=(",", ":"))
    record = report(source)
    assert load_record(ReportRecord, dump_record(record)) == record
    assert dump_json(value, limits=REPORT_CONTENT_LIMITS) == source
    assert parse_json(source, REPORT_CONTENT_LIMITS) == value
    with pytest.raises(JsonError, match="json_resource_limit"):
        dump_json(value)
    with pytest.raises(JsonError, match="json_resource_limit"):
        JsonDocument(source)
    with pytest.raises(ValidationError):
        NormalizedAnswer(question_id="q", option_id="a", probabilities_source=source)


def test_aggregate_source_still_has_an_explicit_byte_bound():
    source = json.dumps({"payload": "x" * REPORT_CONTENT_LIMITS.max_bytes})
    with pytest.raises(ValidationError):
        report(source)
    with pytest.raises(JsonError, match="json_resource_limit"):
        dump_json({"payload": "x" * REPORT_CONTENT_LIMITS.max_bytes}, limits=REPORT_CONTENT_LIMITS)


def test_user_source_bound_remains_one_mebibyte():
    source = '"' + "x" * 1_048_575 + '"'
    assert len(source.encode()) == 1_048_577
    assert report(source).content_source == source
    with pytest.raises(JsonError, match="json_resource_limit"):
        JsonDocument(source)


def test_aggregate_node_and_depth_bounds_remain_enforced():
    too_many_nodes = "[" + ",".join("null" for _ in range(750_000)) + "]"
    with pytest.raises(ValidationError):
        report(too_many_nodes)
    with pytest.raises(ValidationError):
        report("[" * 129 + "null" + "]" * 129)
