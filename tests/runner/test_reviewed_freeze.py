"""Focused receipts and freeze checks for reviewed run/group starts."""

import asyncio

import pytest

from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import semantic_hash
from deykit.contracts.ports import CompilerIdentity, ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord
from deykit.runner.group_selection import (
    decode_group_start_selection,
    encode_group_start_selection,
    group_start_intent,
)
from deykit.runner.planner import RunRequest
from deykit.runner.review import run_review_hash, run_review_payload


def request() -> RunRequest:
    return RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
    )


def test_reviewed_run_hash_binds_exact_captured_plan_and_stale_start_has_no_effects(setup):
    source, runner, factory, _ = setup(count=1)
    plan = runner.planner.prepare(request())
    preview_hash = run_review_hash(plan)
    payload = run_review_payload(plan)
    assert payload["kind"] == "run-review-v1"
    assert payload["compiler"] == ["jev-choice", "1"]
    assert payload["records"]
    assert preview_hash == semantic_hash(payload)

    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            runner.start(
                request(), operation_id="stale-run", expected_review_context_hash="0" * 64
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert factory.calls == []


def test_all_invalid_plan_still_binds_resolved_compiler_identity(setup):
    _source, runner, factory, _ = setup(count=1, invalid=(0,))
    first = runner.planner.prepare(request())
    first_hash = run_review_hash(first)
    assert first.initial_requests == 0
    assert first.prepared[0].error is not None

    class AlternateCompiler:
        review_identity = CompilerIdentity("alternate-choice", "9")

        def compile(self, *_args):
            raise AssertionError("invalid input must not reach the compiler")

    factory.compiler = AlternateCompiler()
    second = runner.planner.prepare(request())
    assert second.initial_requests == 0
    assert second.review_compiler == CompilerIdentity("alternate-choice", "9")
    assert run_review_hash(second) != first_hash
    assert factory.calls == []


def test_original_reviewed_run_replays_before_mutable_preflight(setup):
    source, runner, factory, _ = setup(count=1)
    review_hash = runner.preview(request()).review_context_hash
    original = asyncio.run(
        runner.start(
            request(), operation_id="reviewed-run", expected_review_context_hash=review_hash
        )
    )
    stored = source.read(ResourceKey("cases", "case-00", ("data",)))
    case = load_record(CaseRecord, stored.body)
    source.commit(
        "edit-after-freeze",
        (
            SourceChange(
                stored.key,
                dump_record(case.model_copy(update={"input_source": '{"text":"later"}'})),
                stored.etag,
            ),
        ),
    )
    replay = asyncio.run(
        runner.start(
            request(), operation_id="reviewed-run", expected_review_context_hash=review_hash
        )
    )
    assert replay.run_id == original.run_id
    assert replay.replayed
    assert len(factory.calls) == 1


def test_group_selection_codec_preserves_legacy_bytes_and_binds_review_hash():
    source = '{ "kind" : "choice_order", "request" : {"seed":0} }\n'
    legacy = encode_group_start_selection(source)
    assert legacy.stored_source == source
    assert legacy.expected_review_context_hash is None
    assert group_start_intent(legacy) == semantic_hash(
        {
            "command": "execution_group.start",
            "selection": {"kind": "choice_order", "request": {"seed": 0}},
        }
    )

    reviewed = encode_group_start_selection(
        source, expected_review_context_hash="a" * 64
    )
    decoded = decode_group_start_selection(reviewed.stored_source, expected_kind="choice_order")
    assert decoded.original_selection == legacy.original_selection
    assert decoded.expected_review_context_hash == "a" * 64
    assert group_start_intent(decoded) == semantic_hash(
        {
            "command": "execution_group.start.reviewed-v1",
            "selection": legacy.original_selection,
            "expected_review_context_hash": "a" * 64,
        }
    )


def test_stale_reviewed_group_start_has_no_group_or_dispatch_effects(setup):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    request_value = ChoiceOrderRequest(run=request())
    review_hash = service.preview(request_value).review_context_hash
    stored = source.read(ResourceKey("cases", "case-00", ("data",)))
    case = load_record(CaseRecord, stored.body)
    source.commit(
        "edit-before-freeze",
        (
            SourceChange(
                stored.key,
                dump_record(case.model_copy(update={"input_source": '{"text":"later"}'})),
                stored.etag,
            ),
        ),
    )
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(
                request_value,
                operation_id="stale-group",
                expected_review_context_hash=review_hash,
            )
        )
    assert failure.value.error.code == "conflict"
    assert source.capture_snapshot() == before
    assert source.list_ids("execution_groups") == ()
    assert source.list_ids("runs") == ()
    assert factory.calls == []
