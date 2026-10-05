"""Independent reproductions from P02 review, including persisted corrupt source."""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectService
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    DecisionDraft,
    ExecutionSettings,
    LabelRecord,
    ProjectRecord,
    RunManifest,
    RunSegment,
)
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"


class FixedClock:
    def utc_now(self):
        return STAMP

    def monotonic(self):
        return 0.0


def projects():
    return ProjectService(
        lambda root, create: FileProjectSource(root, create=create), FixedClock(), lambda: "p"
    )


def draft(value):
    return dump_record(DecisionDraft(decision_id="d", editor_source=value, updated_at=STAMP))


def initialized(tmp_path):
    root = tmp_path / "Project"
    projects().create(root, "Project", "create")
    return root


def rejected_mutation(root, expected):
    with FileProjectSource(root) as source, pytest.raises(ServiceFailure) as error:
        source.commit("unrelated", (SourceChange(ResourceKey("drafts", "d"), draft("new"), None),))
    assert error.value.error.reason == expected
    assert not (root / "history/journal/unrelated").exists()


@pytest.mark.parametrize(
    "collection,old_scope,new_scope",
    [
        ("cases", ("Data",), ("data",)),
        ("labels", ("Decision", "Data"), ("decision", "Data")),
        ("labels", ("Decision", "Data"), ("Decision", "data")),
    ],
)
def test_empty_scope_casing_alias_rejected_before_commit_decision(
    tmp_path, collection, old_scope, new_scope
):
    root = initialized(tmp_path)

    def record(scope):
        if collection == "cases":
            return CaseRecord(id="c", dataset_id=scope[0], input_kind="text", input_source='"x"')
        return LabelRecord(
            id="c",
            decision_id=scope[0],
            dataset_id=scope[1],
            case_id="case",
            question_id="q",
            input_hash="a" * 64,
            acceptable_option_ids=("a",),
            provenance="human",
            updated_at=STAMP,
        )

    with FileProjectSource(root) as source:
        old_key = ResourceKey(collection, "c", old_scope)
        stored = source.commit(
            "add", (SourceChange(old_key, dump_record(record(old_scope)), None),)
        ).changes[0]
        source.commit("delete", (SourceChange(old_key, None, stored.etag),))
        assert (root / "source" / collection).joinpath(*old_scope).is_dir()
        new_key = ResourceKey(collection, "c", new_scope)
        with pytest.raises(ServiceFailure) as error:
            source.commit("alias", (SourceChange(new_key, dump_record(record(new_scope)), None),))
        assert error.value.error.reason == "casefold_collision"
        assert not (root / "history/journal/alias").exists()
        assert not (root / "history/operations/alias").exists()
        assert tuple(item.key.collection for item in source.capture_snapshot()) == ("project",)
        assert source.last_index_error is None


@pytest.mark.parametrize("reverse", [False, True])
def test_project_identity_swap_has_no_durable_decision(tmp_path, reverse):
    root = initialized(tmp_path)
    marker = root / "deykit.project.json"
    original = marker.read_bytes()
    with FileProjectSource(root) as source:
        saved = source.read(ResourceKey("project", "p"))
        replacement = ProjectRecord(id="q", name="Replacement", created_at=STAMP)
        changes = (
            SourceChange(saved.key, None, saved.etag),
            SourceChange(ResourceKey("project", "q"), dump_record(replacement), None),
        )
        with pytest.raises(ServiceFailure) as error:
            source.commit("swap", tuple(reversed(changes)) if reverse else changes)
        assert error.value.error.reason == "duplicate_target_path"
        assert marker.read_bytes() == original
        assert not (root / "history/journal/swap").exists()
        assert source.read(saved.key) == saved


def test_project_marker_cannot_be_deleted_and_external_identity_change_is_visible(tmp_path):
    root = initialized(tmp_path)
    marker = root / "deykit.project.json"
    with FileProjectSource(root) as source:
        current = source.read(ResourceKey("project", "p"))
        with pytest.raises(ServiceFailure) as error:
            source.commit("delete", (SourceChange(current.key, None, current.etag),))
        assert error.value.error.reason == "project_identity_immutable"
    changed = dump_record(ProjectRecord(id="q", name="External", created_at=STAMP))
    marker.write_bytes(changed)
    with pytest.raises(ServiceFailure) as error:
        projects().validate(root)
    assert error.value.error.reason == "project_identity_changed"
    rejected_mutation(root, "project_identity_changed")
    assert marker.read_bytes() == changed


@pytest.mark.parametrize("side", ["old", "new"])
@pytest.mark.parametrize("damage", ["corrupt", "missing", "unsupported_version"])
def test_completed_history_blob_integrity_is_globally_required(tmp_path, side, damage):
    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        key = ResourceKey("drafts", "d")
        first = source.commit("d1", (SourceChange(key, draft("before"), None),)).changes[0]
        source.commit("d2", (SourceChange(key, draft("after"), first.etag),))
    folder = root / "history/operations/d2"
    blob = folder / f"{side}-0.json"
    expected = "journal_integrity_error"
    if damage == "missing":
        blob.unlink()
    elif damage == "corrupt":
        blob.write_bytes(b"invalid JSON")
    else:
        value = json.loads(blob.read_bytes())
        value["schema_version"] = 999
        body = json.dumps(value).encode()
        blob.write_bytes(body)
        # Keep hashes internally consistent to independently prove typed/version checking,
        # rather than testing only a digest mismatch.
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["entries"][0][f"{side}_hash"] = hashlib.sha256(body).hexdigest()
        manifest_body = json.dumps(manifest).encode()
        manifest_path.write_bytes(manifest_body)
        marker_path = folder / "commit.json"
        marker = json.loads(marker_path.read_bytes())
        marker["manifest_hash"] = hashlib.sha256(manifest_body).hexdigest()
        marker_path.write_text(json.dumps(marker))
        expected = "invalid_record"
    before = blob.read_bytes() if blob.exists() else None
    with pytest.raises(ServiceFailure) as error:
        projects().validate(root)
    assert error.value.error.reason == expected
    rejected_mutation(root, expected)
    assert (blob.read_bytes() if blob.exists() else None) == before
    assert (root / "source/drafts/d.json").read_bytes() == draft("after")


def cancel_project(tmp_path):
    root = initialized(tmp_path)
    run = RunManifest(
        id="run",
        decision_revision_id="revision",
        dataset_snapshot_id="data",
        label_snapshot_id="labels",
        provider_profile_id="provider",
        provider_config_hash="a" * 64,
        adapter="fixture",
        compiler_version="1",
        requested_model="authored",
        mode="fixture",
        case_ids=("case",),
        settings=ExecutionSettings(),
        created_at=STAMP,
        operation_id="start",
    )
    segment = RunSegment(id="s", run_id="run", started_at=STAMP, deadline_at="2026-10-05T12:10:00Z")
    with FileProjectSource(root) as source:
        source.commit(
            "start",
            (
                SourceChange(ResourceKey("runs", "run"), dump_record(run), None),
                SourceChange(ResourceKey("segments", "s", ("run",)), dump_record(segment), None),
            ),
        )
        source.request_cancel("run")
        with source.execution_owner():
            source.acknowledge_cancel("run", "s")
    return root


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("request_version", "invalid_cancellation"),
        ("ack_version", "invalid_cancellation"),
        ("request_run", "invalid_cancellation"),
        ("missing_run", "cancellation_run_missing"),
        ("missing_segment", "cancellation_segment_missing"),
        ("missing_request", "invalid_cancellation"),
    ],
)
def test_cancellation_history_is_validated_on_open_and_unrelated_commit(tmp_path, damage, expected):
    root = cancel_project(tmp_path)
    request = next((root / "history/cancellations/run").glob("*.json"))
    ack = root / "history/cancel_ack/run/s.json"
    if damage in {"request_version", "request_run"}:
        target = request
        value = json.loads(target.read_bytes())
        value["schema_version" if damage == "request_version" else "run_id"] = (
            999 if damage == "request_version" else "other"
        )
    elif damage == "missing_run":
        directory = root / "history/cancellations/nonexistent"
        directory.mkdir()
        target = directory / "request.json"
        value = {"schema_version": 1, "id": "request", "run_id": "nonexistent", "requested": True}
    else:
        target = ack
        value = json.loads(target.read_bytes())
        if damage == "ack_version":
            value["schema_version"] = 999
        elif damage == "missing_segment":
            value["segment_id"] = "missing"
            target = ack.with_name("missing.json")
            ack.unlink()
        else:
            value["request_ids"] = ["missing"]
    corrupted = json.dumps(value).encode()
    target.write_bytes(corrupted)
    with pytest.raises(ServiceFailure) as error:
        projects().open(root)
    assert error.value.error.reason == expected
    rejected_mutation(root, expected)
    assert target.read_bytes() == corrupted


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX FIFO only; native Windows rejection has its own tests"
)
def test_fifo_source_rejection_is_bounded_and_releases_source_lock(tmp_path):
    root = initialized(tmp_path)
    folder = root / "source/drafts"
    folder.mkdir(parents=True)
    os.mkfifo(folder / "d.json")
    program = """
import sys
from pathlib import Path
from deykit.application.errors import ServiceFailure
from deykit.storage import FileProjectSource
from deykit.storage.locks import acquire
with FileProjectSource(Path(sys.argv[1])) as source:
    try:
        source.capture_snapshot()
    except ServiceFailure as error:
        print(error.error.reason, flush=True)
    with acquire(source.files, "source.lock"):
        print("unlocked", flush=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(root)],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert result.stdout.splitlines() == ["unsafe_source_path", "unlocked"]
