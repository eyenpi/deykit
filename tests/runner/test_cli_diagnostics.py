import json

from typer.testing import CliRunner

from deykit.application.labels import LabelService
from deykit.cli.commands import diagnostics, regressions
from deykit.cli.main import app
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import DispatchOutcome

cli = CliRunner()


def invoke(source, *args):
    return cli.invoke(app, ["--json", "--project", str(source.root), *args])


def diagnose(*extra):
    return (
        "diagnose",
        "choice-order",
        "--decision",
        "decision",
        "--dataset",
        "data",
        "--mode",
        "fixture",
        "--fixture-set",
        "set",
        *extra,
    )


def check(*extra):
    return ("check", "--decision", "decision", "--mode", "fixture", "--fixture-set", "set", *extra)


def test_diagnostic_cli_dry_run_exact_group_and_safe_output(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    monkeypatch.setattr(diagnostics, "service", lambda _: runner)
    before = source.capture_snapshot()
    preview = invoke(source, *diagnose("--dry-run"))
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["data"]["initial_requests"] == 2
    assert not factory.calls and source.capture_snapshot() == before
    first = invoke(source, *diagnose("--operation-id", "start"))
    assert first.exit_code == 0, first.output
    data = json.loads(first.stdout)["data"]
    assert data["summary"]["independent_case_count"] == 1
    assert data["summary"]["expanded_result_count"] == 2
    assert "body" not in first.stdout and "Text 0" not in first.stdout
    group_id = data["group"]["group_id"]
    assert invoke(source, "diagnose", "show", group_id).exit_code == 0
    replay = invoke(source, *diagnose("--operation-id", "start"))
    assert replay.exit_code == 0 and len(factory.calls) == 2
    assert json.loads(replay.stdout)["data"]["group"]["replayed"]


def test_diagnostic_cli_keeps_frozen_labels_and_uses_no_extra_calls(setup, monkeypatch):
    source, runner, factory, clock = setup(count=1)
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="authored_fixture",
        operation_id="first-label",
    )
    monkeypatch.setattr(diagnostics, "service", lambda _: runner)
    first = invoke(source, *diagnose("--operation-id", "start-analysis"))
    assert first.exit_code == 0, first.output
    data = json.loads(first.stdout)["data"]
    assert data["summary"]["evidence_mode"] == "fixture"
    analysis = data["summary"]["order_analysis"]
    assert [item["option_order"] for item in analysis["orders"]] == [["yes", "no"], ["no", "yes"]]
    assert [item["accuracy"]["value"] for item in analysis["orders"]] == ["1.000000", "1.000000"]
    assert analysis["accuracy_gap"]["value"] == "0.000000"
    assert analysis["orders"][1]["flips_from_original"]["numerator"] == 0
    assert analysis["orders"][1]["flips_from_original"]["denominator"] == 1
    assert analysis["cases"][0]["flipped_from_original"] == [None, False]
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("no",),
        provenance="authored_fixture",
        operation_id="second-label",
    )
    later = invoke(source, "diagnose", "show", data["group"]["group_id"])
    assert later.exit_code == 0, later.output
    assert json.loads(later.stdout)["data"]["summary"]["order_analysis"] == analysis
    assert len(factory.calls) == 2


def test_regression_cli_save_expected_sets_mixed_exits_and_remove(setup, monkeypatch):
    source, runner, factory, _ = setup(count=2)
    monkeypatch.setattr(diagnostics, "service", lambda _: runner)
    monkeypatch.setattr(regressions, "service", lambda _: runner)
    result = invoke(source, *diagnose("--orders", "1", "--operation-id", "origin"))
    assert result.exit_code == 0, result.output
    run_id = json.loads(result.stdout)["data"]["group"]["members"][0]["run_id"]
    for index, expected in enumerate(("no", "yes")):
        added = invoke(
            source,
            "regression",
            "add",
            run_id,
            f"case-{index:02}",
            "--expected",
            expected,
            "--reason",
            "Explicit oracle",
            "--operation-id",
            f"reg-{index}",
        )
        assert added.exit_code == 0, added.output
    assert len(factory.calls) == 2
    wrong = invoke(source, *check("--operation-id", "wrong"))
    assert wrong.exit_code == 5, wrong.output
    factory.responses["case-01"] = [
        DispatchOutcome(
            state="known", error=ServiceError(code="provider_rejected", reason="invalid_response")
        )
    ]
    provider_error = invoke(source, *check("--operation-id", "provider"))
    assert provider_error.exit_code == 3, provider_error.output
    factory.responses["case-01"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="run_incomplete", reason="timeout")
        )
    ]
    unknown = invoke(source, *check("--operation-id", "unknown"))
    assert unknown.exit_code == 4, unknown.output
    ids = [
        r["id"]
        for r in json.loads(invoke(source, "regression", "list", "--decision", "decision").stdout)[
            "data"
        ]
    ]
    assert len(ids) == 2
    removed = invoke(
        source, "regression", "remove", ids[0], "--decision", "decision", "--operation-id", "remove"
    )
    assert removed.exit_code == 0, removed.output
    assert len(source.list_ids("regressions")) == 2
