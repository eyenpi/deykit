import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deykit.application.errors import ServiceFailure
from deykit.runner.history import read_history

CHILD = r"""
import asyncio, os, sys, time
from pathlib import Path
from conftest import Clock, Factory
from deykit.application.execution import ExecutionService
from deykit.runner.planner import RunRequest
from deykit.contracts.records import ExecutionSettings
from deykit.storage import FileProjectSource
root, boundary, marker, release, resume_id = sys.argv[1:]
clock, factory = Clock(), Factory()
def mark(value):
    temporary = Path(marker + '.ready')
    temporary.write_text(value, encoding='utf-8')
    os.replace(temporary, marker)
if boundary == 'in_transport':
    async def in_transport(case_id, request):
        mark(str(len(factory.calls)))
        while True:
            await asyncio.sleep(.01)
    factory.callback = in_transport
def hook(stage, attempt):
    if stage == boundary:
        mark(str(len(factory.calls)))
        if release != '-':
            while not Path(release).exists():
                time.sleep(.01)
        else:
            while True:
                time.sleep(.01)
with FileProjectSource(Path(root)) as source:
    service = ExecutionService(source,source,factory,clock,waiter=clock,hook=hook)
    request = RunRequest(
        decision_id='decision', dataset_id='data', mode='fixture', fixture_set_id='set',
        settings=ExecutionSettings(concurrency=1),
    )
    if resume_id == '-':
        result = asyncio.run(service.start(request, operation_id='child-start'))
    else:
        original_ack = source.acknowledge_cancel
        def acknowledge(run_id, segment_id):
            if boundary == 'resume_segment_commit':
                mark('0')
                while True:
                    time.sleep(.01)
            original_ack(run_id, segment_id)
            if boundary == 'resume_legacy_ack':
                mark('0')
                while True:
                    time.sleep(.01)
        source.acknowledge_cancel = acknowledge
        result = asyncio.run(service.resume(resume_id, operation_id='child-resume'))
"""


def killed_exit_code():
    return 1 if os.name == "nt" else -signal.SIGKILL


def kill_at_checkpoint(command, environment, marker):
    child = subprocess.Popen(
        command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "child did not reach the crash checkpoint"
        child.kill()
        _, stderr = child.communicate(timeout=10)
        assert child.returncode == killed_exit_code(), stderr.decode()
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def child_command(source, stage, marker, release="-", resume_id="-"):
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    return [
        sys.executable,
        "-c",
        CHILD,
        str(source.root),
        stage,
        str(marker),
        str(release),
        str(resume_id),
    ], environment


@pytest.mark.parametrize(
    "boundary,actual_calls", [("after_intent", 0), ("after_dispatch", 0), ("after_received", 1)]
)
def test_a23_actual_process_death_preserves_unknown_and_no_open_dispatch(
    setup, tmp_path, boundary, actual_calls
):
    source, service, factory, _ = setup(1)
    marker = tmp_path / "killed"
    command, environment = child_command(source, boundary, marker)
    kill_at_checkpoint(command, environment, marker)
    assert marker.read_text() == str(actual_calls)
    run_id = source.list_ids("runs")[0]
    before = read_history(source, run_id)
    assert before.used == 1 and before.final_event(before.attempts[0].id).state in {
        "reserved",
        "dispatched",
    }
    recovered = service.show(run_id)
    assert factory.calls == [] and recovered.state == "interrupted"
    assert recovered.cases[0].status == "unknown" and recovered.attempts_used == 1
    assert service.preview_resume(run_id).planned_case_ids == ()
    assert service.preview_resume(run_id, retry_unknown=True).planned_case_ids == ("case-00",)
    resumed = asyncio.run(service.resume(run_id, operation_id="resume", retry_unknown=True))
    assert (
        resumed.attempts_used == 2
        and resumed.cases[0].status == "valid"
        and len(factory.calls) == 1
    )
    assert len(read_history(source, run_id).attempts) == 2


def test_a25_actual_owner_prevents_takeover_or_false_interruption(setup, tmp_path):
    import time

    from test_execution import request

    source, service, factory, _ = setup(2)
    marker, release = tmp_path / "active", tmp_path / "release"
    command, environment = child_command(source, "after_dispatch", marker, release)
    child = subprocess.Popen(
        command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        timeout = time.monotonic() + 20
        while not marker.exists() and child.poll() is None and time.monotonic() < timeout:
            time.sleep(0.01)
        assert marker.exists()
        run_id = source.list_ids("runs")[0]
        history = read_history(source, run_id)
        boundary = history.boundary
        active = service.show(run_id)
        assert active.execution_active and active.state == "running"
        assert read_history(source, run_id).boundary == boundary
        from deykit.contracts.records import ExecutionSettings

        replayed = asyncio.run(
            service.start(
                request(settings=ExecutionSettings(concurrency=1)), operation_id="child-start"
            )
        )
        assert replayed.replayed and replayed.execution_active and replayed.run_id == run_id
        assert read_history(source, run_id).boundary == boundary
        with pytest.raises(ServiceFailure) as raised:
            asyncio.run(service.resume(run_id, operation_id="competing"))
        assert raised.value.error.code == "execution_locked"
        with pytest.raises(ServiceFailure) as raised:
            asyncio.run(service.start(request(), operation_id="second-start"))
        assert raised.value.error.code == "execution_locked"
        assert factory.calls == []
        service.cancel(run_id, operation_id="external-cancel")
        release.write_text("go")
        _, stderr = child.communicate(timeout=30)
        assert child.returncode == 0, stderr.decode()
        settled = service.show(run_id)
        assert settled.state == "cancelled"
        assert [case.status for case in settled.cases] == ["valid", "pending"]
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)


def test_receipt_recheck_covers_freeze_between_lookup_and_owner_contention(
    setup, tmp_path, monkeypatch
):
    import time
    from contextlib import contextmanager

    from test_execution import request

    from deykit.contracts.records import ExecutionSettings

    source, service, factory, _ = setup(1)
    marker, release = tmp_path / "race-active", tmp_path / "race-release"
    command, environment = child_command(source, "after_dispatch", marker, release)
    original_owner = source.execution_owner
    children = []

    @contextmanager
    def acquire_after_other_process_freezes():
        # Called after the parent's first receipt lookup returned None.
        # Subsequent ownership probes must not launch another competing child.
        if not children:
            child = subprocess.Popen(
                command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            children.append(child)
            timeout = time.monotonic() + 20
            while not marker.exists() and child.poll() is None and time.monotonic() < timeout:
                time.sleep(0.01)
            assert marker.exists()
        with original_owner():
            yield

    monkeypatch.setattr(source, "execution_owner", acquire_after_other_process_freezes)
    try:
        result = asyncio.run(
            service.start(
                request(settings=ExecutionSettings(concurrency=1)), operation_id="child-start"
            )
        )
        assert result.replayed and result.execution_active and result.attempts_used == 1
        assert not factory.calls
    finally:
        release.write_text("go")
        for child in children:
            try:
                _, stderr = child.communicate(timeout=30)
                assert child.returncode == 0, stderr.decode()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=5)


def test_a23_kill_with_transport_entered_before_response(setup, tmp_path):
    import time

    source, service, factory, _ = setup(1)
    marker = tmp_path / "in-flight"
    command, environment = child_command(source, "in_transport", marker)
    child = subprocess.Popen(
        command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        timeout = time.monotonic() + 20
        while not marker.exists() and child.poll() is None and time.monotonic() < timeout:
            time.sleep(0.01)
        assert marker.read_text() == "1"
        child.kill()
        child.communicate(timeout=5)
        assert child.returncode == killed_exit_code()
        run_id = source.list_ids("runs")[0]
        recovered = service.show(run_id)
        assert recovered.cases[0].status == "unknown" and recovered.attempts_used == 1
        assert not factory.calls and service.preview_resume(run_id).planned_case_ids == ()
        repeated = asyncio.run(service.resume(run_id, operation_id="explicit", retry_unknown=True))
        assert repeated.attempts_used == 2 and repeated.cases[0].status == "valid"
        assert len(factory.calls) == 1
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)


@pytest.mark.parametrize("boundary", ["resume_segment_commit", "resume_legacy_ack"])
def test_resume_death_before_readiness_never_replays_ack_or_consumes_new_cancel(
    setup, tmp_path, boundary
):
    from test_execution import request

    source, service, factory, _ = setup(1)
    stopped = asyncio.run(
        service.start(
            request(),
            operation_id="start",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )
    source.request_cancel(stopped.run_id)
    marker = tmp_path / "resume-death"
    command, environment = child_command(source, boundary, marker, resume_id=stopped.run_id)
    kill_at_checkpoint(command, environment, marker)
    assert marker.read_text() == "0"
    # After a completed legacy ack this creates a distinct new request; otherwise
    # it preserves the still-pending request. Replay must acknowledge neither.
    source.request_cancel(stopped.run_id)
    callbacks = []
    with pytest.raises(ServiceFailure) as caught:
        asyncio.run(
            service.resume(stopped.run_id, operation_id="child-resume", on_resumed=callbacks.append)
        )
    assert caught.value.error.reason == "resume_acknowledgement_incomplete"
    assert caught.value.error.resource_id == stopped.run_id
    assert not callbacks and not factory.calls and source.cancellation_requested(stopped.run_id)
    assert service.show(stopped.run_id).state == "interrupted"
    resumed = asyncio.run(service.resume(stopped.run_id, operation_id="new-explicit-resume"))
    assert resumed.exit_code == 0 and len(factory.calls) == 1
