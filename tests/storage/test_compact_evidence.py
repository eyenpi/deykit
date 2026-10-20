"""Compact immutable evidence is exact, durable, and readable beside legacy files."""

import os

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import RunEvent
from deykit.storage import FileProjectSource
from deykit.storage.journal import CommitDecision, JournalEntry, JournalManifest


def events(count=8, prefix="event"):
    return tuple(
        SourceChange(
            ResourceKey("run_events", f"{prefix}-{i}", ("run",)),
            dump_record(
                RunEvent(
                    id=f"{prefix}-{i}",
                    run_id="run",
                    sequence=i + 1,
                    state="running",
                    created_at="2026-10-20T00:00:00Z",
                )
            ),
            None,
        )
        for i in range(count)
    )


def test_compact_round_trip_replay_and_bounded_physical_files(tmp_path):
    changes = events()
    with FileProjectSource(tmp_path / "project", create=True) as source:
        receipt = source.commit("compact", changes, intent_hash="a" * 64)
        assert len(list((source.root / "history/operations/compact").iterdir())) <= 4
        assert not list((source.root / "source/run_events").rglob("*.json"))
        assert {r.key: r.body for r in receipt.changes} == {c.key: c.body for c in changes}
        assert source.operation_receipt("compact", intent_hash="a" * 64).changes == receipt.changes
        assert source.commit("compact", changes, intent_hash="a" * 64).replayed
    with FileProjectSource(tmp_path / "project") as reopened:
        assert {r.key: r.body for r in reopened.capture_snapshot()} == {
            c.key: c.body for c in changes
        }
        assert reopened.operation_history(changes[-1].key)[0].after.body == changes[-1].body
        assert reopened.rebuild_index() == len(changes)


def test_legacy_and_compact_evidence_coexist(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        (old,) = events(1, "legacy")
        entry = JournalEntry(
            collection=old.key.collection,
            resource_id=old.key.resource_id,
            scope=old.key.scope,
            old_hash=None,
            new_hash=bytes_hash(old.body),
        )
        manifest = JournalManifest(
            operation_id="legacy",
            payload_hash=source._payload((old,)),
            sequence=1,
            entries=(entry,),
        )
        body = dump_record(manifest)
        folder = ("history", "operations", "legacy")
        source.files.replace((*folder, "manifest.json"), body)
        source.files.replace(
            (*folder, "commit.json"),
            dump_record(CommitDecision(operation_id="legacy", manifest_hash=bytes_hash(body))),
        )
        source.files.replace((*folder, "new-0.json"), old.body)
        source.files.replace(
            ("source", "run_events", "run", old.key.resource_id + ".json"), old.body
        )
        source.commit("compact", events(3))
        assert len(source.capture_snapshot()) == 4
        assert source.read(old.key).body == old.body


@pytest.mark.parametrize(
    "point,committed",
    [
        ("staged:0", False),
        ("prepared", False),
        ("decided", True),
        ("applied:0", True),
        ("archived", True),
    ],
)
def test_compact_recovers_after_every_decision_boundary(tmp_path, point, committed):
    root = tmp_path / "project"

    def crash(stage):
        if stage == point:
            raise OSError("authored interruption")

    with FileProjectSource(root, create=True, fault_hook=crash) as source:
        with pytest.raises(ServiceFailure):
            source.commit("operation", events())
    with FileProjectSource(root) as reopened:
        assert len(reopened.capture_snapshot()) == (8 if committed else 0)
        assert reopened.capture_snapshot() == reopened.capture_snapshot()


def test_compact_corruption_is_not_hidden_by_warm_validation(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        source.commit("compact", events())
        source.read_records()
        (chunk,) = tuple((source.root / "history/operations/compact").glob("*.pack"))
        body = chunk.read_bytes()
        info = chunk.stat()
        chunk.write_bytes(body[:-1] + bytes([body[-1] ^ 1]))
        os.utime(chunk, ns=(info.st_atime_ns, info.st_mtime_ns))
        with pytest.raises(ServiceFailure):
            source.read_records()


@pytest.mark.parametrize("removed", ["archive", "reference"])
def test_missing_compact_operation_or_reference_is_detected(tmp_path, removed):
    import shutil

    with FileProjectSource(tmp_path / "project", create=True) as source:
        source.commit("compact", events())
        source.read_records()
        if removed == "archive":
            shutil.rmtree(source.root / "history/operations/compact")
        else:
            (source.root / "source/_chunks/compact.json").unlink()
        with pytest.raises(ServiceFailure):
            source.read_records()


def test_physical_file_cannot_shadow_compact_evidence(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        changes = events()
        source.commit("compact", changes)
        source.files.replace(("source", "run_events", "run", "event-0.json"), changes[0].body)
        with pytest.raises(ServiceFailure) as failure:
            source.read_records()
        assert failure.value.error.reason == "immutable_source_changed"


def test_multiple_chunks_and_exact_numeric_input_bytes(tmp_path, monkeypatch):
    from deykit.contracts.records import CaseRecord
    from deykit.storage import _chunks

    monkeypatch.setattr(_chunks, "_TARGET_BYTES", 400)
    changes = tuple(
        SourceChange(
            ResourceKey("cases", f"case-{i}", ("data",)),
            dump_record(
                CaseRecord(
                    id=f"case-{i}",
                    dataset_id="data",
                    input_kind="json",
                    input_source='{"big":9007199254740993,"d":0.1234567890123456789,"s":"é"}',
                )
            ),
            None,
        )
        for i in range(16)
    )
    with FileProjectSource(tmp_path / "project", create=True) as source:
        source.commit("compact", changes)
        chunks = list((source.root / "history/operations/compact").glob("*.pack"))
        assert len(chunks) > 1
        assert {r.key: r.body for r in source.read_records()} == {c.key: c.body for c in changes}
        last = chunks[-1]
        body = last.read_bytes()
        last.unlink()
        with pytest.raises(ServiceFailure):
            source.read_records()
        last.write_bytes(body)
        assert source.read(changes[-1].key).body == changes[-1].body


@pytest.mark.parametrize(
    "damage", ["truncated", "trailing", "duplicate", "index", "kind", "length", "version"]
)
def test_framing_rejects_corruption_even_with_a_matching_outer_hash(damage):
    import struct

    from deykit.storage._chunks import ChunkManifest, decode_chunks, encode_chunks

    (change,) = events(1)
    (valid,) = encode_chunks(((0, False, change.body),))
    header = len(b"DEYKIT-BLOBS\x00\x01")
    variants = {
        "truncated": valid[:-1],
        "trailing": valid + b"x",
        "duplicate": valid + valid[header:],
        "index": valid[:header] + struct.pack(">I", 99) + valid[header + 4 :],
        "kind": valid[: header + 4] + b"\x02" + valid[header + 5 :],
        "length": valid[: header + 5]
        + struct.pack(">I", 16 * 1024 * 1024 + 1)
        + valid[header + 9 :],
        "version": valid[: header - 1] + b"\x02" + valid[header:],
    }
    damaged = variants[damage]
    manifest = ChunkManifest(
        operation_id="compact",
        payload_hash="a" * 64,
        sequence=1,
        entries=(
            JournalEntry(
                collection=change.key.collection,
                resource_id=change.key.resource_id,
                scope=change.key.scope,
                old_hash=None,
                new_hash=bytes_hash(change.body),
            ),
        ),
        blob_chunks=(bytes_hash(damaged),),
    )
    with pytest.raises(ServiceFailure) as failure:
        decode_chunks(manifest, (damaged,))
    assert failure.value.error.reason == "journal_integrity_error"


@pytest.mark.parametrize("point", ["decided", "applied:0", "chunk_linked"])
def test_real_process_death_preserves_committed_compact_intent(tmp_path, point):
    import subprocess
    import sys

    root = tmp_path / "project"
    script = """
import os,sys
from pathlib import Path
from deykit.storage import FileProjectSource
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey,SourceChange
from deykit.contracts.records import RunEvent
def hook(point):
    if point==sys.argv[2]: os._exit(73)
with FileProjectSource(Path(sys.argv[1]),create=True,fault_hook=hook) as source:
    source.commit('compact',tuple(SourceChange(ResourceKey('run_events',f'event-{i}',('run',)),
        dump_record(RunEvent(id=f'event-{i}',run_id='run',sequence=i+1,state='running',
        created_at='2026-10-20T00:00:00Z')),None) for i in range(8)))
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(root), point], capture_output=True, timeout=10
    )
    assert child.returncode == 73, child.stderr.decode()
    with FileProjectSource(root) as source:
        assert len(source.read_records()) == 8
        assert source.commit("compact", events()).replayed
        assert len(source.read_records()) == 8


def test_compact_copy_does_not_depend_on_disposable_cache(tmp_path):
    import shutil

    root = tmp_path / "project"
    with FileProjectSource(root, create=True) as source:
        receipt = source.commit("compact", events(), intent_hash="a" * 64)
        expected = source.capture_snapshot()
    copied = tmp_path / "Copied project é"
    shutil.copytree(root, copied)
    shutil.rmtree(copied / ".deykit", ignore_errors=True)
    with FileProjectSource(copied) as reader:
        assert reader.capture_snapshot() == expected
        assert reader.operation_receipt("compact", intent_hash="a" * 64).changes == receipt.changes


def test_lock_free_compact_receipt_uses_fresh_bytes(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        receipt = source.commit("compact", events(), intent_hash="a" * 64)
        source.read_records()

        def forbidden(*args):
            raise AssertionError("lock-free peek used validation memo")

        monkeypatch.setattr(source._operation_validation, "get", forbidden)
        monkeypatch.setattr(source._journal_validation, "load", forbidden)
        assert (
            source._peek_durable_receipt("compact", intent_hash="a" * 64).changes == receipt.changes
        )


def test_pending_compact_operation_preserves_external_mutable_conflict(tmp_path):
    from deykit.contracts.records import CaseRecord

    key = ResourceKey("cases", "case", ("data",))

    def case(text):
        return dump_record(
            CaseRecord(
                id="case", dataset_id="data", input_kind="text", input_source='"' + text + '"'
            )
        )

    root = tmp_path / "project"
    with FileProjectSource(root, create=True) as source:
        saved = source.commit("initial", (SourceChange(key, case("before"), None),)).changes[0]

        def stop(point):
            if point == "decided":
                raise OSError("authored interruption")

        source._hook = stop
        with pytest.raises(ServiceFailure):
            source.commit("mixed", (*events(), SourceChange(key, case("after"), saved.etag)))
    target = root / "source/cases/data/case.json"
    target.write_bytes(case("external"))
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure) as failure:
            source.read_records()
        assert failure.value.error.reason == "recovery_source_conflict"
    assert target.read_bytes() == case("external")
    assert not (root / "source/_chunks/mixed.json").exists()
