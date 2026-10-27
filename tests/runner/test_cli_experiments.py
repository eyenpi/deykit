import json
from contextlib import contextmanager

from test_experiments import experiment
from typer.testing import CliRunner

from deykit.cli.main import app


def test_experiment_cli_requires_review_and_recovers(tmp_path, setup, monkeypatch):
    from deykit.cli.commands import experiments
    from deykit.cli.context import CliState

    source, runner, factory, _ = setup(count=2)
    request = experiment(source)

    @contextmanager
    def source_context(_self):
        yield source

    monkeypatch.setattr(CliState, "source", source_context)
    monkeypatch.setattr(experiments, "service", lambda _: runner)
    config = tmp_path / "experiment.json"
    config.write_text(request.model_dump_json(), encoding="utf-8")
    cli = CliRunner()

    def invoke(*args):
        return cli.invoke(app, ["--project", str(source.root), "--json", "experiments", *args])

    preview = invoke("preview", str(config))
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["data"]["group"]["initial_requests"] == 4
    review = tmp_path / "review.json"
    review.write_text(preview.stdout, encoding="utf-8")
    missing = invoke("run", str(config), "--operation-id", "start")
    assert missing.exit_code == 2 and not factory.calls
    result = invoke("run", str(config), "--preview", str(review), "--operation-id", "start")
    assert result.exit_code == 4, result.output
    data = json.loads(result.stdout)["data"]
    group_id = data["group"]["group_id"]
    assert f"Created fixture experiment {group_id}" in result.stderr
    assert data["reserved_usd"] == "0.30" and len(factory.calls) == 3
    assert invoke("show", group_id).exit_code == 0
    retry = invoke("resume", group_id, "--dry-run")
    assert retry.exit_code == 0
    assert len(factory.calls) == 3
    report = invoke("report", group_id, "--snapshot", data["group"]["snapshot_id"])
    assert report.exit_code == 0, report.output
    report_data = json.loads(report.stdout)["data"]
    assert report_data["snapshot_id"] == data["group"]["snapshot_id"]
    assert len(report_data["members"]) == 2
    assert sum(member["selected_cases"] for member in report_data["members"]) == 4
    assert sum(member["status_counts"]["pending"] for member in report_data["members"]) == 1
    assert "Text 0" not in report.stdout and len(factory.calls) == 3
    cancelled = invoke("cancel", group_id, "--operation-id", "cancel")
    assert cancelled.exit_code == 0 and len(factory.calls) == 3, cancelled.output


def test_experiment_review_accepts_a_preview_larger_than_a_stored_record(tmp_path, monkeypatch):
    from deykit.cli.commands import experiments
    from deykit.contracts.json_value import JsonLimits

    monkeypatch.setattr(experiments, "RECORD_LIMITS", JsonLimits(max_bytes=256))
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "data": {
                    "group": {
                        "kind": "experiment",
                        "dry_run": True,
                        "review_context_hash": "a" * 64,
                    },
                    "padding": "x" * 1000,
                },
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    assert experiments._review_hash(review) == "a" * 64


def test_experiment_config_reads_only_up_to_its_limit(monkeypatch):
    import io

    import pytest

    from deykit.cli.commands import experiments
    from deykit.contracts.json_value import JsonError, JsonLimits

    reads = []

    class Stream(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class Config:
        def open(self, mode):
            assert mode == "rb"
            return Stream(b"x" * 100)

        def read_bytes(self):
            raise AssertionError("unbounded read")

    monkeypatch.setattr(experiments, "RECORD_LIMITS", JsonLimits(max_bytes=32))
    with pytest.raises(JsonError) as failure:
        experiments._request(Config())
    assert failure.value.code == "json_resource_limit" and reads == [33]


def test_experiment_preview_does_not_emit_an_unreadable_review(tmp_path, setup, monkeypatch):
    from deykit.cli.commands import experiments
    from deykit.cli.context import CliState
    from deykit.contracts.json_value import JsonLimits

    source, runner, factory, _ = setup(count=2)

    @contextmanager
    def source_context(_self):
        yield source

    monkeypatch.setattr(CliState, "source", source_context)
    monkeypatch.setattr(experiments, "service", lambda _: runner)
    monkeypatch.setattr(
        experiments, "EXPERIMENT_PREVIEW_LIMITS", JsonLimits(max_bytes=256), raising=False
    )
    config = tmp_path / "experiment.json"
    config.write_text(experiment(source).model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        app, ["--project", str(source.root), "--json", "experiments", "preview", str(config)]
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["reason"] == "experiment_preview_resource_limit"
    assert not factory.calls


def test_active_experiment_show_waits_for_a_busy_source(setup, monkeypatch):
    import asyncio

    from deykit.application.errors import ServiceFailure
    from deykit.application.experiments import ExperimentService
    from deykit.cli.commands import experiments
    from deykit.cli.context import CliState
    from deykit.contracts.errors import ServiceError

    source, runner, _factory, _ = setup(count=1)
    request = experiment(source, budget="0.20")
    result = asyncio.run(ExperimentService(runner).start(request, operation_id="start"))
    original_read = source.consistent_read
    calls = 0

    @contextmanager
    def busy_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ServiceFailure(ServiceError(code="conflict", reason="source_busy"))
        with original_read() as captured:
            yield captured

    @contextmanager
    def source_context(_self):
        yield source

    monkeypatch.setattr(source, "consistent_read", busy_once)
    monkeypatch.setattr(runner.execution, "execution_active", lambda: True)
    monkeypatch.setattr(CliState, "source", source_context)
    monkeypatch.setattr(experiments, "service", lambda _: runner)
    observed = CliRunner().invoke(app, ["--json", "experiments", "show", result.group_id])
    assert observed.exit_code == 0, observed.output
    assert json.loads(observed.stdout)["data"]["group"]["group_id"] == result.group_id
    assert calls > 1


def test_cancel_waits_for_another_priority_reader(setup, monkeypatch):
    import asyncio

    from deykit.application.errors import ServiceFailure
    from deykit.application.experiments import ExperimentService
    from deykit.cli.commands import experiments
    from deykit.cli.context import CliState
    from deykit.contracts.errors import ServiceError

    source, runner, _factory, _ = setup(count=1)
    result = asyncio.run(
        ExperimentService(runner).start(experiment(source, budget="0.20"), operation_id="start")
    )
    original = source.priority_read
    calls = 0

    @contextmanager
    def busy_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ServiceFailure(ServiceError(code="conflict", reason="source_busy"))
        with original():
            yield

    @contextmanager
    def source_context(_self):
        yield source

    monkeypatch.setattr(source, "priority_read", busy_once)
    monkeypatch.setattr(CliState, "source", source_context)
    monkeypatch.setattr(experiments, "service", lambda _: runner)
    observed = CliRunner().invoke(
        app, ["--json", "experiments", "cancel", result.group_id, "--operation-id", "cancel"]
    )
    assert observed.exit_code == 0, observed.output
    assert calls > 1


def test_waiting_progress_reader_gets_next_source_epoch(setup):
    import pytest

    from deykit.application.errors import ServiceFailure
    from deykit.storage import FileProjectSource

    writer, _, _, _ = setup(count=1)
    with FileProjectSource(writer.root) as reader, FileProjectSource(writer.root) as competitor:
        epoch = writer.consistent_read()
        epoch.__enter__()
        try:
            with reader.priority_read():
                epoch.__exit__(None, None, None)
                epoch = None
                with pytest.raises(ServiceFailure) as failure:
                    with competitor.consistent_read():
                        pass
                assert failure.value.error.reason == "source_priority"
                with reader.consistent_read():
                    assert reader.capture_snapshot()
        finally:
            if epoch is not None:
                epoch.__exit__(None, None, None)
        with competitor.consistent_read():
            assert competitor.capture_snapshot()


def test_priority_reader_handoff_and_process_death_release(setup, tmp_path):
    import subprocess
    import sys
    import time

    import pytest

    from deykit.application.errors import ServiceFailure
    from deykit.storage import FileProjectSource

    writer, _, _, _ = setup(count=1)
    ready, acquired = tmp_path / "ready", tmp_path / "acquired"
    program = """
import sys, time
from pathlib import Path
from deykit.application.errors import ServiceFailure
from deykit.storage import FileProjectSource
with FileProjectSource(Path(sys.argv[1])) as source:
    with source.priority_read():
        Path(sys.argv[2]).write_text('ready')
        while True:
            try:
                with source.consistent_read():
                    source.capture_snapshot()
                    Path(sys.argv[3]).write_text('acquired')
                break
            except ServiceFailure as error:
                if error.error.reason != 'source_busy':
                    raise
                time.sleep(0.01)
        while True:
            time.sleep(1)
"""

    def wait_for(path, process):
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.01)
        assert path.exists(), f"child did not create {path.name}: {process.poll()}"

    process = None
    try:
        with FileProjectSource(writer.root) as competitor:
            with writer.consistent_read():
                process = subprocess.Popen(
                    [sys.executable, "-c", program, str(writer.root), str(ready), str(acquired)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                wait_for(ready, process)
                assert not acquired.exists()
                with pytest.raises(ServiceFailure) as failure:
                    with competitor.consistent_read():
                        pass
                assert failure.value.error.reason == "source_priority"
            wait_for(acquired, process)
            process.terminate()
            process.communicate(timeout=10)
            with competitor.consistent_read():
                assert competitor.capture_snapshot()
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_scheduler_waits_for_priority_reader_without_resetting_dispatch_deadline(setup):
    import asyncio

    import pytest

    from deykit.runner.scheduler import _SegmentDeadlineElapsed
    from deykit.storage import FileProjectSource

    source, runner, _, clock = setup(count=1)
    with FileProjectSource(source.root) as reader:
        priority = reader.priority_read()
        priority.__enter__()
        released = False

        class ReleaseWaiter:
            async def wait(self, seconds):
                nonlocal released
                clock.value += seconds
                if clock.value >= 6 and not released:
                    priority.__exit__(None, None, None)
                    released = True

        runner.scheduler.waiter = ReleaseWaiter()
        try:
            result = asyncio.run(runner.scheduler._source_call("run", "history", lambda: "ready"))
            assert result == "ready" and clock.value >= 6
        finally:
            if not released:
                priority.__exit__(None, None, None)

        clock.value = 0
        with reader.priority_read():
            with pytest.raises(_SegmentDeadlineElapsed):
                asyncio.run(
                    runner.scheduler._source_call("run", "reservation", lambda: None, deadline=3)
                )
        assert clock.value >= 3
