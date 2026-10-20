"""Repeated history admission must not allocate lookup keys for every source record."""

import asyncio

import pytest
from test_execution import request

from deykit.runner import history


@pytest.mark.parametrize("damage", ["changed", "removed", "appended"])
def test_incremental_admission_rejects_changed_or_invalid_evidence(setup, damage):
    from deykit.application.errors import ServiceFailure
    from deykit.contracts.codec import dump_record, load_record
    from deykit.contracts.json_value import bytes_hash
    from deykit.contracts.ports import ResourceKey, StoredRecord
    from deykit.contracts.records import AttemptEvent

    source, service, _, _ = setup(1)
    result = asyncio.run(service.start(request(), operation_id="run"))
    records = source.read_records()
    service.repository._history_index.capture(records, result.run_id)
    original = next(r for r in records if r.key.collection == "attempt_events")
    event = load_record(AttemptEvent, original.body)
    if damage == "removed":
        altered = tuple(r for r in records if r is not original)
    else:
        value = event.model_copy(
            update={"sequence": 99, "id": "bad" if damage == "appended" else event.id}
        )
        body = dump_record(value)
        record = StoredRecord(
            ResourceKey("attempt_events", value.id, original.key.scope), body, bytes_hash(body)
        )
        altered = (
            (*records, record)
            if damage == "appended"
            else tuple(record if r is original else r for r in records)
        )
    with pytest.raises(ServiceFailure) as incremental:
        service.repository._history_index.capture(altered, result.run_id)
    with pytest.raises(ServiceFailure) as rebuilt:
        history.history_from_records(altered, result.run_id)
    assert incremental.value.error == rebuilt.value.error


def test_append_only_history_validates_only_new_attempt_transitions(setup, monkeypatch):
    from deykit.contracts.records import ExecutionSettings
    from deykit.runner import _history_index

    source, service, factory, _ = setup(64)
    calls = []
    original = history.validate_attempt

    def observe(attempt, *args):
        calls.append(attempt.id)
        return original(attempt, *args)

    monkeypatch.setattr(history, "validate_attempt", observe)
    monkeypatch.setattr(_history_index, "validate_attempt", observe)
    snapshots = []

    def check(progress):
        records = source.read_records()
        incremental = service.repository.history(progress.run_id)
        rebuilt = history.history_from_records(records, progress.run_id)
        assert incremental == rebuilt
        assert incremental.results() == rebuilt.results()
        snapshots.append(incremental)

    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=64, concurrency=16)),
            operation_id="run",
            on_progress=check,
        )
    )
    assert result.state == "completed" and len(factory.calls) == 64
    assert snapshots
    # Explicit comparison rebuilds above are verification work, excluded from the bound.
    comparison_calls = sum(len(s.attempts) for s in snapshots)
    assert len(calls) - comparison_calls <= 4 * 64


def test_run_lookup_builds_one_scoped_key(setup, monkeypatch):
    source, service, _, _ = setup(1)
    result = asyncio.run(service.start(request(), operation_id="run"))
    captured = source.read_records()
    calls = []
    original = history.ResourceKey

    def observe(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(history, "ResourceKey", observe)
    assert history.history_from_records(captured, result.run_id).manifest.id == result.run_id
    assert calls == [("runs", result.run_id)]
