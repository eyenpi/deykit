import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from deykit.application.errors import ServiceFailure
from deykit.runner.history import read_history

CHILD = r"""
import asyncio, os, signal, sys, time
from pathlib import Path
from conftest import Clock, Factory
from deykit.application.execution import ExecutionService
from deykit.runner.planner import RunRequest
from deykit.contracts.records import ExecutionSettings
from deykit.storage import FileProjectSource
root, boundary, marker, release = sys.argv[1:]
clock, factory = Clock(), Factory()
def hook(stage, attempt):
    if stage == boundary:
        Path(marker).write_text(str(len(factory.calls)))
        if release != '-':
            while not Path(release).exists():
                time.sleep(.01)
        else:
            os.kill(os.getpid(), signal.SIGKILL)
with FileProjectSource(Path(root)) as source:
    service = ExecutionService(source,source,factory,clock,waiter=clock,hook=hook)
    request = RunRequest(
        decision_id='decision', dataset_id='data', mode='fixture', fixture_set_id='set',
        settings=ExecutionSettings(concurrency=1),
    )
    result = asyncio.run(service.start(request, operation_id='child-start'))
"""


def child_command(source, stage, marker, release="-"):
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    return [
        sys.executable,
        "-c",
        CHILD,
        str(source.root),
        stage,
        str(marker),
        str(release),
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
    child = subprocess.run(command, env=environment, capture_output=True, timeout=30)
    assert child.returncode == -signal.SIGKILL, child.stderr.decode()
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
