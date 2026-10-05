import subprocess
import sys
import time

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectService
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import ExecutionSettings, ProjectRecord, RunManifest
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"


CHILD = """
import sys
from pathlib import Path
from deykit.storage import FileProjectSource
with FileProjectSource(Path(sys.argv[1])) as source:
    with source.execution_owner():
        print('owned',flush=True)
        sys.stdin.read()
"""


def test_actual_process_ownership_and_process_death_release(tmp_path):
    with FileProjectSource(tmp_path, create=True) as source:
        assert not source.execution_active()
    process = subprocess.Popen(
        [sys.executable, "-c", CHILD, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdout.readline().splitlines() == [b"owned"]
        with FileProjectSource(tmp_path) as source:
            assert source.execution_active()
            with pytest.raises(ServiceFailure) as error:
                with source.execution_owner():
                    pass
            assert error.value.error.code == "execution_locked"
        process.kill()
        process.wait(timeout=10)
        with FileProjectSource(tmp_path) as source:
            deadline = time.monotonic() + 10
            while source.execution_active() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert not source.execution_active()
            with source.execution_owner():
                pass
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_source_and_execution_locks_are_separate_and_ordered(tmp_path):
    with FileProjectSource(tmp_path, create=True) as first, FileProjectSource(tmp_path) as second:
        with first.execution_owner():
            with second.consistent_read():
                with pytest.raises(ServiceFailure) as error:
                    with second.execution_owner():
                        pass
                assert error.value.error.reason == "lock_order_violation"
        with first.consistent_read():
            with first.consistent_read():
                assert first.capture_snapshot() == ()
            with pytest.raises(ServiceFailure) as error:
                second.capture_snapshot()
            assert error.value.error.reason == "source_busy"


def test_cancel_is_durable_while_execution_owner_holds_lock(tmp_path):
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
    with FileProjectSource(tmp_path, create=True) as owner, FileProjectSource(tmp_path) as caller:
        owner.commit("start", (SourceChange(ResourceKey("runs", "run"), dump_record(run), None),))
        with owner.execution_owner():
            assert not caller.cancellation_requested("run")
            caller.request_cancel("run")
            assert owner.cancellation_requested("run")
    with FileProjectSource(tmp_path) as reopened:
        assert reopened.cancellation_requested("run")


def test_open_project_does_not_classify_live_owner_interrupted(tmp_path):
    with FileProjectSource(tmp_path, create=True) as owner:
        project = ProjectRecord(id="p", name="Project", created_at=STAMP)
        owner.commit(
            "create", (SourceChange(ResourceKey("project", "p"), dump_record(project), None),)
        )

        class Clock:
            def utc_now(self):
                raise AssertionError("open must not generate an execution timestamp")

            def monotonic(self):
                return 0.0

        service = ProjectService(
            lambda root, create: FileProjectSource(root, create=create), Clock(), lambda: "unused"
        )
        with owner.execution_owner():
            assert service.open(tmp_path).execution_active
        assert not service.open(tmp_path).execution_active


def test_resume_acknowledges_only_prior_cancel_and_preserves_history(tmp_path):
    from deykit.contracts.records import RunSegment

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
    with FileProjectSource(tmp_path, create=True) as source:
        segment = RunSegment(
            id="resume", run_id="run", started_at=STAMP, deadline_at="2026-10-05T12:10:00Z"
        )
        source.commit(
            "start",
            (
                SourceChange(ResourceKey("runs", "run"), dump_record(run), None),
                SourceChange(
                    ResourceKey("segments", "resume", ("run",)), dump_record(segment), None
                ),
            ),
        )
        source.request_cancel("run")
        with pytest.raises(ServiceFailure) as error:
            source.acknowledge_cancel("run", "resume")
        assert error.value.error.reason == "execution_ownership_required"
        with source.execution_owner():
            source.acknowledge_cancel("run", "resume")
            assert not source.cancellation_requested("run")
            source.request_cancel("run")
            assert source.cancellation_requested("run")
            with pytest.raises(ServiceFailure) as error:
                source.acknowledge_cancel("run", "resume")
            assert error.value.error.reason == "new_cancellation_requires_new_segment"
    assert len(list((tmp_path / "history/cancellations/run").glob("*.json"))) == 2
    assert len(list((tmp_path / "history/cancel_ack/run").glob("*.json"))) == 1
