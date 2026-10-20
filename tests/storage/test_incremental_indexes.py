"""Derived indexes scale with changes while their source remains independently fresh."""

from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.storage import FileProjectSource
from deykit.storage.index import SourceIndex


def test_recovery_admission_cannot_stand_in_for_current_integrity():
    import pytest

    from deykit.application.errors import ServiceFailure
    from deykit.contracts.codec import dump_record
    from deykit.contracts.json_value import bytes_hash
    from deykit.contracts.records import RunEvent
    from deykit.storage._history_capture import OperationEvidence
    from deykit.storage._integrity_index import IntegrityIndex
    from deykit.storage._source_view import CapturedView
    from deykit.storage.records import key_path

    key = ResourceKey("run_events", "event", ("run",))
    old = RunEvent(
        id="event", run_id="run", sequence=1, state="running", created_at="2026-10-20T00:00:00Z"
    )
    body = dump_record(old.model_copy(update={"state": "cancelled"}))
    changed = StoredRecord(key, body, bytes_hash(body))
    evidence = (OperationEvidence(1, ((key, bytes_hash(dump_record(old))),)),)
    records = (changed,)
    view = CapturedView(
        records, evidence, records, frozenset(), {key: changed}, ((key_path(key), changed),)
    )
    index = IntegrityIndex()
    index.check(evidence, records, view, check_current=False)
    with pytest.raises(ServiceFailure) as error:
        index.check(evidence, records, view, check_current=True)
    assert error.value.error.reason == "immutable_source_changed"


def test_sqlite_rebuild_encodes_only_changed_scopes(tmp_path, monkeypatch):
    from deykit.storage import index

    records = tuple(
        StoredRecord(ResourceKey("cases", f"case-{i}", ("data",)), b"{}", "a" * 64)
        for i in range(64)
    )
    calls = []
    original = index.json.dumps

    def encode(value, *args, **kwargs):
        calls.append(value)
        return original(value, *args, **kwargs)

    with FileProjectSource(tmp_path / "project", create=True) as source:
        monkeypatch.setattr(index.json, "dumps", encode)
        cache = SourceIndex(source.files)
        try:
            cache.rebuild(records)
            cache.rebuild(
                (*records, StoredRecord(ResourceKey("cases", "added", ("data",)), b"{}", "b" * 64))
            )
            assert len(calls) == 65
        finally:
            close = getattr(cache, "close", None)
            if close:
                close()
