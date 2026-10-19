"""Journal parsing reuse never replaces fresh bytes or history validation."""

import os

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import JsonError
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft
from deykit.storage import FileProjectSource
from deykit.storage import _journal_validation as journal_validation
from deykit.storage import source as source_module
from deykit.storage.journal import CommitDecision, JournalManifest


def warmed_source(tmp_path):
    source = FileProjectSource(tmp_path / "journal", create=True)
    key = ResourceKey("drafts", "draft")
    body = dump_record(
        DecisionDraft(
            decision_id="draft", editor_source="authored", updated_at="2026-10-19T00:00:00Z"
        )
    )
    source.commit("operation", (SourceChange(key, body, None),), intent_hash="a" * 64)
    source.read(key)
    return source, key


def test_repeated_reads_do_not_reparse_unchanged_journal_bytes(tmp_path, monkeypatch):
    source, key = warmed_source(tmp_path)
    source.read(key)
    original = source_module.load_record
    calls = []

    def counted(kind, body):
        if kind in (JournalManifest, CommitDecision):
            calls.append(kind)
        return original(kind, body)

    monkeypatch.setattr(source_module, "load_record", counted)
    monkeypatch.setattr(journal_validation, "load_record", counted)
    for _ in range(3):
        assert source.read(key) is not None
    assert calls == []
    source.close()


@pytest.mark.parametrize("name", ["manifest.json", "commit.json", "new-0.json"])
def test_warm_journal_still_rejects_changed_bytes_with_preserved_metadata(tmp_path, name):
    source, key = warmed_source(tmp_path)
    source.read(key)
    path = source.root / "history/operations/operation" / name
    before = path.read_bytes()
    info = path.stat()
    changed = before.replace(b'"schema_version":1', b'"schema_version":2', 1)
    assert len(changed) == len(before) and changed != before
    path.write_bytes(changed)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    with pytest.raises(ServiceFailure):
        source.read(key)
    source.close()


def test_warm_journal_still_detects_extra_files(tmp_path):
    source, key = warmed_source(tmp_path)
    source.read(key)
    (source.root / "history/operations/operation/extra.json").write_bytes(b"{}")
    with pytest.raises(ServiceFailure) as error:
        source.read(key)
    assert error.value.error.reason == "journal_integrity_error"
    source.close()


def test_journal_memo_bounds_types_failures_and_close(tmp_path, monkeypatch):
    source, key = warmed_source(tmp_path)
    source.read(key)
    folder = source.root / "history/operations/operation"
    manifest = (folder / "manifest.json").read_bytes()
    marker = (folder / "commit.json").read_bytes()
    original = journal_validation.load_record
    calls = []

    def counted(kind, body):
        calls.append((kind, body))
        return original(kind, body)

    monkeypatch.setattr(journal_validation, "load_record", counted)
    monkeypatch.setattr(journal_validation, "_MAX_ENTRIES", 1)
    memo = journal_validation._SuccessfulJournalValidationMemo()
    memo.load(JournalManifest, manifest)
    memo.load(JournalManifest, manifest)
    memo.load(CommitDecision, marker)
    memo.load(JournalManifest, manifest)
    assert len(calls) == 3
    for _ in range(2):
        with pytest.raises(JsonError):
            memo.load(JournalManifest, marker)
    assert len(calls) == 5
    assert len(memo._entries) == 1
    memo.clear()
    monkeypatch.setattr(journal_validation, "_MAX_RETAINED_BYTES", len(manifest) - 1)
    for _ in range(2):
        memo.load(JournalManifest, manifest)
    assert len(calls) == 7 and not memo._entries
    assert source._journal_validation._entries
    source.close()
    assert not source._journal_validation._entries
    assert source._journal_validation._retained_bytes == 0


def test_lock_free_receipt_peek_bypasses_journal_memo(tmp_path, monkeypatch):
    source, _ = warmed_source(tmp_path)
    assert source._journal_validation._entries

    def forbidden(*args):
        pytest.fail("lock-free receipt inspection must parse fresh journal records")

    monkeypatch.setattr(source._journal_validation, "load", forbidden)
    receipt = source._peek_durable_receipt("operation", intent_hash="a" * 64)
    assert receipt is not None and receipt.replayed
    source.close()


def test_empty_journal_avoids_duplicate_recovery_validation(tmp_path, monkeypatch):
    source, key = warmed_source(tmp_path)
    scans = []
    checks = []
    original_all, original_check = source._all, source._check_integrity

    def scan():
        scans.append(True)
        return original_all()

    def check(records, *, check_current=True):
        checks.append(check_current)
        return original_check(records, check_current=check_current)

    monkeypatch.setattr(source, "_all", scan)
    monkeypatch.setattr(source, "_check_integrity", check)
    assert source.read(key) is not None
    assert len(scans) == 2
    assert checks == [True, True]
    source.close()


def test_corrupt_history_blocks_discarding_pending_recovery(tmp_path):
    source, key = warmed_source(tmp_path)
    current = source.read(key)

    def stop(point):
        if point == "prepared":
            raise OSError("injected interruption before decision")

    source._hook = stop
    with pytest.raises(ServiceFailure):
        source.commit("pending", (SourceChange(key, current.body, current.etag),))
    pending = source.root / "history/journal/pending"
    assert pending.exists()
    source._hook = lambda _: None
    (source.root / "history/operations/operation/new-0.json").write_bytes(b"tampered")
    with pytest.raises(ServiceFailure) as error:
        source.read(key)
    assert error.value.error.reason == "journal_integrity_error"
    assert pending.exists()
    assert (source.root / "source/drafts/draft.json").read_bytes() == current.body
    source.close()
