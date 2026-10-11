"""Pinned group snapshot reads remain independent from mutable group progress."""

import asyncio

import pytest

from deykit.application.checks import CheckRequest, CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.runner.planner import RunRequest


def _run_request():
    return RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )


def test_diagnostic_snapshot_reader_is_pinned_and_read_only(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    diagnostics = DiagnosticService(runner)
    started = asyncio.run(
        diagnostics.start(
            ChoiceOrderRequest(run=_run_request(), orders=2, seed=0), operation_id="diagnose"
        )
    )
    choices = diagnostics.list_snapshots(started.group.group_id)
    assert choices
    selected = choices[-1]
    before_read = source.capture_snapshot()
    monkeypatch.setattr(diagnostics.groups, "show", lambda *_a, **_k: pytest.fail("show used"))
    monkeypatch.setattr(
        runner.execution, "execution_active", lambda: pytest.fail("recovery probe used")
    )
    detail = diagnostics.read_snapshot(started.group.group_id, selected.id)
    assert detail.snapshot.id == selected.id
    assert detail.snapshot.results == selected.results
    assert tuple(member.results.id for member in detail.members) == tuple(
        result.result_snapshot_id for result in selected.results
    )
    assert detail.summary.independent_case_count == 1
    assert source.capture_snapshot() == before_read
    assert len(factory.calls) == 2

    with pytest.raises(ServiceFailure) as wrong_group:
        diagnostics.read_snapshot("missing-group", selected.id)
    assert wrong_group.value.error.reason == "diagnostic_snapshot_mismatch"


def test_check_snapshot_survives_current_regression_removal(setup, monkeypatch):
    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(_run_request(), operation_id="origin"))
    regression = RegressionService(source, clock, lambda: "m12-regression").add(
        RegressionAdd(
            run_id=origin.run_id,
            case_id="case-00",
            acceptable_option_ids=("no",),
            reason="Authored frozen expectation.",
        ),
        operation_id="save-regression",
    )
    checks = CheckService(runner)
    started = asyncio.run(
        checks.start(
            CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="set"),
            operation_id="check",
        )
    )
    selected = checks.list_snapshots(started.group.group_id)[-1]
    assert selected.results

    RegressionService(source, clock).remove(
        regression.id, decision_id="decision", operation_id="remove-regression"
    )
    before_read = source.capture_snapshot()
    monkeypatch.setattr(checks.groups, "show", lambda *_a, **_k: pytest.fail("show used"))
    monkeypatch.setattr(
        runner.execution, "execution_active", lambda: pytest.fail("recovery probe used")
    )
    detail = checks.read_snapshot(started.group.group_id, selected.id)
    assert detail.snapshot.id == selected.id
    assert detail.expectation_failures == 1
    assert detail.cases[0].regression_id == regression.id
    assert detail.cases[0].passed is False
    assert detail.baseline_unavailable == "frozen_regression_selection"
    assert detail.members[0].results.id == selected.results[0].result_snapshot_id
    assert detail.members[0].labels.id
    assert source.capture_snapshot() == before_read
    assert len(factory.calls) == 2

    with pytest.raises(ServiceFailure) as wrong_kind:
        DiagnosticService(runner).read_snapshot(started.group.group_id, selected.id)
    assert wrong_kind.value.error.reason == "diagnostic_snapshot_missing"
