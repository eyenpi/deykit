import subprocess
import sys

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, LabelRecord
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"
CASE = ResourceKey("cases", "c", ("data",))
LABEL = ResourceKey("labels", "l", ("decision", "data"))


def pair(value):
    case = CaseRecord(id="c", dataset_id="data", input_kind="text", input_source=f'"{value}"')
    label = LabelRecord(
        id="l",
        decision_id="decision",
        dataset_id="data",
        case_id="c",
        question_id="q",
        input_hash="a" * 64,
        acceptable_option_ids=(value,),
        provenance="human",
        updated_at=STAMP,
    )
    return dump_record(case), dump_record(label)


def seed(root):
    with FileProjectSource(root, create=True) as source:
        a, b = pair("old")
        return source.commit("seed", (SourceChange(CASE, a, None), SourceChange(LABEL, b, None)))


CHILD = r"""
import os,sys
from pathlib import Path
from deykit.storage import FileProjectSource
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey,SourceChange
from deykit.contracts.records import CaseRecord,LabelRecord
root=Path(sys.argv[1]); checkpoint=sys.argv[2]; recovering=sys.argv[3]=='recover'
def hook(point):
    if point==checkpoint: os._exit(73)
with FileProjectSource(root,fault_hook=hook) as source:
    if recovering:
        source.capture_snapshot()
    else:
        case=ResourceKey('cases','c',('data',))
        label=ResourceKey('labels','l',('decision','data'))
        a=CaseRecord(id='c',dataset_id='data',input_kind='text',input_source='"new"')
        b=LabelRecord(id='l',decision_id='decision',dataset_id='data',case_id='c',question_id='q',
                      input_hash='b'*64,acceptable_option_ids=('new',),provenance='human',
                      updated_at='2026-10-05T12:00:00Z')
        source.commit('change',(SourceChange(case,dump_record(a),source.read(case).etag),
                                SourceChange(label,dump_record(b),source.read(label).etag)))
"""


def crash(root, checkpoint, *, recovery=False):
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(root), checkpoint, "recover" if recovery else "write"],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 73, result.stderr.decode()


def values(root):
    with FileProjectSource(root) as source:
        records = {record.key: record for record in source.capture_snapshot()}
        return (
            load_record(CaseRecord, records[CASE].body).input_source,
            load_record(LabelRecord, records[LABEL].body).acceptable_option_ids[0],
        )


@pytest.mark.parametrize(
    "checkpoint,expected",
    [
        ("staged:0", "old"),
        ("staged:1", "old"),
        ("prepared", "old"),
        ("decided", "new"),
        ("applied:0", "new"),
        ("applied:1", "new"),
        ("archived", "new"),
    ],
)
def test_a06_process_death_at_every_transaction_boundary(tmp_path, checkpoint, expected):
    root = tmp_path / "project"
    seed(root)
    crash(root, checkpoint)
    assert values(root) == (f'"{expected}"', expected)
    assert values(root) == (f'"{expected}"', expected)  # Reopen is repeatable.
    assert not list((root / "history/journal").iterdir())


@pytest.mark.parametrize("checkpoint", ["applied:0", "applied:1", "recovered"])
def test_process_death_during_recovery_itself(tmp_path, checkpoint):
    root = tmp_path / "project"
    seed(root)
    crash(root, "decided")
    crash(root, checkpoint, recovery=True)
    assert values(root) == ('"new"', "new")
    with FileProjectSource(root) as source:
        assert len(source.operation_history(CASE)) == 2
        assert len(source.operation_history(LABEL)) == 2


def test_fsync_failure_before_decision_does_not_mutate_source(tmp_path, monkeypatch):
    root = tmp_path / "project"
    seed(root)

    def fail_staging(handle):
        raise OSError("SECRET disk failure")

    with FileProjectSource(root) as source:
        current = source.read(CASE)
        a, _ = pair("new")
        with monkeypatch.context() as context:
            context.setattr(source.files._backend, "_flush_file", fail_staging)
            with pytest.raises(ServiceFailure) as error:
                source.commit("failure", (SourceChange(CASE, a, current.etag),))
            assert error.value.error.reason == "storage_io"
            assert "SECRET" not in str(error.value)
    assert values(root) == ('"old"', "old")


def test_corrupt_staged_blob_blocks_recovery_without_partial_replacement(tmp_path):
    root = tmp_path / "project"
    seed(root)
    crash(root, "decided")
    (root / "history/journal/change/new-1.json").write_bytes(b"corrupt")
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure) as error:
            source.capture_snapshot()
        assert error.value.error.reason == "journal_integrity_error"
    assert b"old" in (root / "source/cases/data/c.json").read_bytes()
    assert b"old" in (root / "source/labels/decision/data/l.json").read_bytes()


def test_external_conflict_after_decision_is_preserved(tmp_path):
    root = tmp_path / "project"
    seed(root)
    crash(root, "decided")
    external, _ = pair("external")
    (root / "source/cases/data/c.json").write_bytes(external)
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure) as error:
            source.capture_snapshot()
        assert error.value.error.reason == "recovery_source_conflict"
    assert (root / "source/cases/data/c.json").read_bytes() == external
    assert b"old" in (root / "source/labels/decision/data/l.json").read_bytes()
