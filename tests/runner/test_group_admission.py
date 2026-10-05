"""Independent corruption, immutable-boundary, cancellation and recovery probes."""

import asyncio
from dataclasses import replace

import pytest
from test_execution_groups import request

from deykit.application.diagnostics import (
    ChoiceOrderRequest,
    DiagnosticService,
    diagnostic_snapshot_from_records,
)
from deykit.application.errors import ServiceFailure
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.execution_groups import ExecutionGroupSegment
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DispatchOutcome, RegressionRecord
from deykit.regressions.evidence import admit_regression_origin, regression_hash
from deykit.runner.group_evidence import admit_group_snapshots, content_hash


def changed(records, key, record):
    body = dump_record(record)
    return tuple(
        replace(r, body=body, etag=bytes_hash(body)) if r.key == key else r for r in records
    )


def test_pinned_diagnostic_and_all_retained_corruption_admitted_before_repair(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    snapshot_id = result.group.snapshot_id
    original = diagnostic_snapshot_from_records(source.capture_snapshot(), snapshot_id)
    asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    records = source.capture_snapshot()
    assert diagnostic_snapshot_from_records(records, snapshot_id) == original
    key = ResourceKey("diagnostic_snapshots", snapshot_id)
    snapshot = original.snapshot
    later = next(
        s for s in admit_group_snapshots(records, result.group.group_id) if s.id != snapshot_id
    )
    # Both a rehashed old boundary linked to a later segment and a foreign result are invalid.
    corruptions = [
        snapshot.model_copy(update={"segment_id": later.segment_id}),
        snapshot.model_copy(update={"results": tuple(reversed(snapshot.results))}),
        snapshot.model_copy(update={"results": (snapshot.results[0], snapshot.results[0])}),
        snapshot.model_copy(update={"id": "wrong-path"}),
        snapshot.model_copy(update={"group_id": "absent-group"}),
    ]
    for forged in corruptions:
        forged = forged.model_copy(update={"content_hash": content_hash(forged)})
        batch = changed(records, key, forged)
        # Remove final summary too: malformed retained graph must reject before repair.
        batch = tuple(r for r in batch if r.key != ResourceKey("diagnostic_snapshots", later.id))
        with monkeypatch.context() as patch:
            patch.setattr(source, "capture_snapshot", lambda *args, **kwargs: batch)
            with pytest.raises(ServiceFailure):
                service.read(result.group.group_id)
        assert source.capture_snapshot() == records
    with pytest.raises(ServiceFailure) as error:
        diagnostic_snapshot_from_records((*records, records[0]), snapshot_id)
    assert error.value.error.reason == "duplicate_captured_key"
    segment_record = next(r for r in records if r.key.collection == "group_segments")
    segment = load_record(ExecutionGroupSegment, segment_record.body)
    forged = segment.model_copy(update={"deadline_at": "2026-10-06T00:00:00Z"})
    with pytest.raises(ServiceFailure):
        admit_group_snapshots(changed(records, segment_record.key, forged), result.group.group_id)
    assert len(factory.calls) == 2


def test_terminal_missing_snapshot_repair_is_idempotent_zero_send(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    snapshot = service.groups.store.snapshot

    def fail_snapshot(*args):
        raise ServiceFailure(ServiceError(code="internal_error", reason="injected_snapshot_io"))

    monkeypatch.setattr(service.groups.store, "snapshot", fail_snapshot)
    with pytest.raises(ServiceFailure):
        asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    assert source.list_ids("diagnostic_snapshots") == () and len(factory.calls) == 2
    members = tuple(
        r
        for r in source.capture_snapshot()
        if r.key.collection in {"runs", "segments", "result_snapshots", "run_events"}
    )
    monkeypatch.setattr(service.groups.store, "snapshot", snapshot)
    group_id = source.list_ids("execution_groups")[0]
    repaired = service.read(group_id)
    assert repaired.summary.independent_case_count == 1
    assert len(source.list_ids("diagnostic_snapshots")) == 1
    assert service.read(group_id).group.snapshot_id == repaired.group.snapshot_id
    assert len(factory.calls) == 2
    assert (
        tuple(
            r
            for r in source.capture_snapshot()
            if r.key.collection in {"runs", "segments", "result_snapshots", "run_events"}
        )
        == members
    )


def test_regression_rehashed_origin_metadata_and_attempt_forgery(setup):
    source, runner, factory, clock = setup(count=1)
    run = asyncio.run(runner.start(request(), operation_id="origin"))
    saved = RegressionService(source, clock, lambda: "reg").add(
        RegressionAdd(
            run_id=run.run_id, case_id="case-00", acceptable_option_ids=("yes",), reason="Oracle"
        ),
        operation_id="save",
    )
    records = source.capture_snapshot()
    record = load_record(RegressionRecord, source.read(ResourceKey("regressions", saved.id)).body)
    for update in (
        {"source_attempt_id": "foreign-attempt"},
        {"decision_revision_id": "foreign-revision"},
        {"source_run_id": "foreign-run"},
        {"source_case": record.source_case.model_copy(update={"tags": ("forged",)})},
    ):
        forged = record.model_copy(update=update)
        forged = forged.model_copy(update={"content_hash": regression_hash(forged)})
        with pytest.raises(ServiceFailure):
            admit_regression_origin(records, forged)
    assert len(factory.calls) == 1 and source.capture_snapshot() == records


def test_group_cancellation_stops_current_child_and_old_cutoff_does_not_cancel_resume(setup):
    from conftest import answer

    source, runner, factory, _ = setup(count=3)
    service = DiagnosticService(runner)
    cancelled = []

    async def callback(case_id, body):
        if not cancelled:
            group_id = source.list_ids("execution_groups")[0]
            progress = service.groups.show(group_id)
            later = progress.members[1].run_id
            runner.cancel(later, operation_id="later-cancel")
            cancelled.append(later)
        return answer()

    factory.callback = callback
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    assert len(factory.calls) == 1
    assert result.exit_code == 4
    assert all(m.state == "cancelled" for m in result.group.members)
    factory.callback = None
    resumed = asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert resumed.exit_code == 0 and len(factory.calls) == 6
    assert resumed.group.attempts_used == 6


def test_provider_wide_failure_resume_zero_write(setup):
    source, runner, factory, _ = setup(count=1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            provider_wide=True,
            error=ServiceError(code="provider_rejected", reason="authentication_failed"),
        )
    ]
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as error:
        asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert error.value.error.reason == "provider_wide_failure_requires_new_run"
    assert len(factory.calls) == 1 and source.capture_snapshot() == before


def test_resume_receipt_inside_source_lock_leaves_lock_before_render(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    service = DiagnosticService(runner)
    result = asyncio.run(service.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    real_receipt = source.operation_receipt
    calls = []

    def receipt(operation_id, *, intent_hash):
        calls.append(operation_id)
        # First pre-owner lookup simulates a receipt not yet visible. The second
        # lookup happens inside source ownership and finds the actual committed receipt.
        return None if len(calls) == 1 else real_receipt(operation_id, intent_hash=intent_hash)

    monkeypatch.setattr(source, "operation_receipt", receipt)
    before = source.capture_snapshot()
    replay = asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert replay.group.replayed and len(factory.calls) == 2
    assert source.capture_snapshot() == before
