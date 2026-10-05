"""Real process death at group dispatch boundaries, retaining one lifetime budget."""

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.contracts.records import ExecutionSettings
from deykit.runner.planner import RunRequest

CHILD = r"""
import asyncio, os, time, sys
from pathlib import Path
from conftest import Clock, Factory
from deykit.application.execution import ExecutionService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.runner.planner import RunRequest
from deykit.contracts.records import ExecutionSettings
from deykit.storage import FileProjectSource
root, boundary, marker = sys.argv[1:]
clock, factory = Clock(), Factory()
def stop():
    temp = Path(marker + ".pending")
    temp.write_text(str(len(factory.calls)))
    os.replace(temp, marker)
    while True:
        time.sleep(1)
async def dispatch(case_id, request):
    stop()
if boundary == 'in_transport':
    factory.callback = dispatch
def hook(stage, attempt):
    if stage == boundary:
        stop()
with FileProjectSource(Path(root)) as source:
    runner = ExecutionService(source, source, factory, clock, waiter=clock, hook=hook)
    request = ChoiceOrderRequest(run=RunRequest(decision_id='decision', dataset_id='data',
        mode='fixture', fixture_set_id='set',
        settings=ExecutionSettings(max_attempts=3, concurrency=1)))
    asyncio.run(DiagnosticService(runner).start(request, operation_id='killed-start'))
"""


@pytest.mark.parametrize(
    "stage,calls", [("after_intent", 0), ("in_transport", 1), ("after_received", 1)]
)
def test_process_death_group_replay_and_explicit_unknown_retry(setup, tmp_path, stage, calls):
    source, runner, factory, _ = setup(count=1)
    marker = tmp_path / "marker"
    root = Path(__file__).parents[2]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(root / "src"), str(Path(__file__).parent))),
    }
    with subprocess.Popen(
        [sys.executable, "-c", CHILD, str(source.root), stage, str(marker)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as child:
        try:
            deadline = time.monotonic() + 30
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists(), "child did not reach checkpoint"
            child.kill()
            _, errors = child.communicate(timeout=10)
            assert child.returncode == (1 if os.name == "nt" else -signal.SIGKILL), errors.decode()
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
    assert marker.read_text() == str(calls)
    service = DiagnosticService(runner)
    group_id = source.list_ids("execution_groups")[0]
    recovered = service.read(group_id)
    assert recovered.group.attempts_used == 1 and len(factory.calls) == 0
    assert recovered.group.members[0].cases[0].status == "unknown"
    assert recovered.group.members[1].cases[0].status == "pending"
    request = ChoiceOrderRequest(
        run=RunRequest(
            decision_id="decision",
            dataset_id="data",
            mode="fixture",
            fixture_set_id="set",
            settings=ExecutionSettings(max_attempts=3, concurrency=1),
        )
    )
    replay = asyncio.run(service.start(request, operation_id="killed-start"))
    assert replay.group.replayed and len(factory.calls) == 0
    resumed = asyncio.run(service.resume(group_id, operation_id="continue"))
    assert resumed.group.attempts_used == 2 and len(factory.calls) == 1
    assert resumed.group.members[0].cases[0].status == "unknown"
    retried = asyncio.run(service.resume(group_id, operation_id="retry", retry_unknown=True))
    assert retried.group.attempts_used == 3 and len(factory.calls) == 2
    assert retried.group.attempts_remaining == 0 and retried.exit_code == 0
