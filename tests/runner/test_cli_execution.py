import json

import pytest
from typer.testing import CliRunner

from deykit.cli.commands import execution
from deykit.cli.main import app
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import DispatchOutcome

cli = CliRunner()


def invoke(source, *arguments):
    return cli.invoke(app, ["--json", "--project", str(source.root), *arguments])


def run_args(*more):
    return (
        "run",
        "--decision",
        "decision",
        "--dataset",
        "data",
        "--mode",
        "fixture",
        "--fixture-set",
        "set",
        *more,
    )


def test_cli_run_preview_replay_history_and_safe_output(setup, monkeypatch):
    source, service, factory, _ = setup(2)
    monkeypatch.setattr(execution, "service", lambda _source: service)
    before = source.capture_snapshot()
    preview = invoke(source, *run_args("--case", "case-00", "--dry-run"))
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["data"]["selected_case_ids"] == ["case-00"]
    assert not factory.calls and source.capture_snapshot() == before
    first = invoke(source, *run_args("--operation-id", "start"))
    assert first.exit_code == 0, first.output
    data = json.loads(first.stdout)["data"]
    assert len(factory.calls) == 2 and data["run"]["attempts_used"] == 2
    assert "Created fixture run" in first.stderr
    assert "body" not in first.stdout and "Text 0" not in first.stdout
    repeated = invoke(source, *run_args("--operation-id", "start"))
    assert repeated.exit_code == 0 and json.loads(repeated.stdout)["data"]["run"]["replayed"]
    assert len(factory.calls) == 2
    shown = invoke(source, "runs", "show", data["run"]["run_id"])
    assert shown.exit_code == 0 and json.loads(shown.stdout)["data"]["segments"]
    listed = invoke(source, "runs", "list", "--limit", "1")
    assert json.loads(listed.stdout)["data"]["total"] == 1


def test_cli_unknown_exit_precedence_and_explicit_resume(setup, monkeypatch):
    source, service, factory, _ = setup(3, invalid=(2,))
    monkeypatch.setattr(execution, "service", lambda _source: service)
    factory.responses = {
        "case-00": [
            DispatchOutcome(
                state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
            )
        ],
        "case-01": [
            DispatchOutcome(
                state="known",
                error=ServiceError(code="provider_rejected", reason="invalid_response"),
            )
        ],
    }
    first = invoke(source, *run_args("--operation-id", "start"))
    assert first.exit_code == 4, first.output
    run_id = json.loads(first.stdout)["data"]["run"]["run_id"]
    preview = invoke(source, "runs", "resume", run_id, "--dry-run")
    assert preview.exit_code == 0 and json.loads(preview.stdout)["data"]["planned_case_ids"] == []
    preview = invoke(source, "runs", "resume", run_id, "--dry-run", "--retry-unknown")
    assert json.loads(preview.stdout)["data"]["planned_case_ids"] == ["case-00"]
    assert len(factory.calls) == 2
    resumed = invoke(
        source, "runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume"
    )
    assert resumed.exit_code == 3 and len(factory.calls) == 3
    assert "Resumed run" in resumed.stderr
    shown = invoke(source, "runs", "show", run_id)
    assert shown.exit_code == 0
    repeated = invoke(
        source, "runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume"
    )
    assert repeated.exit_code == 3 and len(factory.calls) == 3


@pytest.mark.parametrize(
    "extra",
    [
        ("--attempt-limit", "1"),
        ("--mode", "implicit"),
        ("--rate-retries", "2"),
        ("--concurrency", "65"),
        ("--timeout-seconds", "0"),
    ],
)
def test_cli_invalid_preflight_zero_calls_and_no_run(setup, monkeypatch, extra):
    source, service, factory, _ = setup(2)
    monkeypatch.setattr(execution, "service", lambda _source: service)
    result = invoke(source, *run_args(*extra))
    assert result.exit_code == 2 and not factory.calls and not source.list_ids("runs")


def test_cli_fixture_requires_explicit_matching_set(setup):
    source, _, factory, _ = setup(1)
    result = invoke(
        source, "run", "--decision", "decision", "--dataset", "data", "--mode", "fixture"
    )
    assert result.exit_code == 2 and not factory.calls and not source.list_ids("runs")
