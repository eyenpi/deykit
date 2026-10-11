"""Pinned group snapshot reads remain independent from mutable group progress."""

import asyncio
from dataclasses import replace

import pytest

from deykit.application.checks import CheckRequest, CheckService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DispatchOutcome, ExecutionSettings
from deykit.runner.group_evidence import content_hash
from deykit.runner.planner import RunRequest


def _run_request(settings: ExecutionSettings | None = None):
    return RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
        settings=settings if settings is not None else ExecutionSettings(),
    )


def test_diagnostic_snapshot_reader_is_pinned_and_read_only(setup, monkeypatch):
    source, runner, factory, _ = setup(count=1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown",
            error=ServiceError(code="provider_rejected", reason="disconnect"),
        ),
        DispatchOutcome(
            state="unknown",
            error=ServiceError(code="provider_rejected", reason="disconnect"),
        ),
    ]
    diagnostics = DiagnosticService(runner)
    request = ChoiceOrderRequest(
        run=_run_request(ExecutionSettings(max_attempts=4, concurrency=1)),
        orders=2,
        seed=0,
    )
    started = asyncio.run(diagnostics.start(request, operation_id="diagnose"))
    choices = diagnostics.list_snapshots(started.group.group_id)
    assert choices
    selected = choices[0]
    resumed = asyncio.run(
        diagnostics.resume(
            started.group.group_id,
            operation_id="diagnostic-resume",
            retry_unknown=True,
        )
    )
    assert resumed.group.attempts_used == 4
    latest_choices = diagnostics.list_snapshots(started.group.group_id)
    assert len(latest_choices) == 2
    assert latest_choices[0].id == selected.id
    assert latest_choices[1].sequence > selected.sequence

    second_group = asyncio.run(diagnostics.start(request, operation_id="other-diagnose"))
    foreign = diagnostics.list_snapshots(second_group.group.group_id)[0]
    captures = 0
    commits = []
    original_capture = source.capture_snapshot
    original_commit = source.commit

    def counted_capture():
        nonlocal captures
        captures += 1
        return original_capture()

    def counted_commit(*args, **kwargs):
        commits.append((args, kwargs))
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(source, "capture_snapshot", counted_capture)
    monkeypatch.setattr(source, "commit", counted_commit)
    monkeypatch.setattr(diagnostics.groups, "show", lambda *_a, **_k: pytest.fail("show used"))
    monkeypatch.setattr(
        runner.execution, "execution_active", lambda: pytest.fail("recovery probe used")
    )
    snapshots = diagnostics.list_snapshots(started.group.group_id)
    assert tuple(item.id for item in snapshots) == tuple(
        item.id for item in latest_choices
    )
    assert captures == 1
    assert not commits
    detail = diagnostics.read_snapshot(started.group.group_id, selected.id)
    assert detail.snapshot.id == selected.id
    assert detail.snapshot.results == selected.results
    assert tuple(member.results.id for member in detail.members) == tuple(
        result.result_snapshot_id for result in selected.results
    )
    assert detail.summary.independent_case_count == 1
    assert captures == 2
    assert not commits

    selected_again = diagnostics.read_snapshot(started.group.group_id, selected.id)
    assert selected_again.snapshot == detail.snapshot
    assert tuple(member.results.id for member in selected_again.members) == tuple(
        member.results.id for member in detail.members
    )
    assert captures == 3
    assert not commits

    with pytest.raises(ServiceFailure) as foreign_snapshot:
        diagnostics.read_snapshot(started.group.group_id, foreign.id)
    assert foreign_snapshot.value.error.reason == "diagnostic_snapshot_mismatch"
    with pytest.raises(ServiceFailure) as wrong_group:
        diagnostics.read_snapshot("missing-group", selected.id)
    assert wrong_group.value.error.reason == "diagnostic_snapshot_mismatch"

    stored = source.read(ResourceKey("diagnostic_snapshots", selected.id))
    assert stored is not None
    broken_result = selected.results[0].model_copy(update={"result_snapshot_id": "missing-result"})
    broken = selected.model_copy(update={"results": (broken_result,)})
    broken = broken.model_copy(update={"content_hash": content_hash(broken)})
    body = dump_record(broken)
    bad_stored = replace(stored, body=body, etag=bytes_hash(body))
    original_records = original_capture()
    corrupted_records = tuple(
        bad_stored if item.key == stored.key else item for item in original_records
    )
    monkeypatch.setattr(source, "capture_snapshot", lambda: corrupted_records)
    with pytest.raises(ServiceFailure) as corrupt_reference:
        diagnostics.list_snapshots(started.group.group_id)
    assert corrupt_reference.value.error.reason == "group_snapshot_context_mismatch"
    assert len(factory.calls) == 6


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
    captures = 0
    commits = []
    original_capture = source.capture_snapshot
    original_commit = source.commit

    def counted_capture():
        nonlocal captures
        captures += 1
        return original_capture()

    def counted_commit(*args, **kwargs):
        commits.append((args, kwargs))
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(source, "capture_snapshot", counted_capture)
    monkeypatch.setattr(source, "commit", counted_commit)
    snapshots_after_removal = checks.list_snapshots(started.group.group_id)
    assert snapshots_after_removal[-1].id == selected.id
    detail = checks.read_snapshot(started.group.group_id, selected.id)
    assert detail.snapshot.id == selected.id
    assert detail.expectation_failures == 1
    assert detail.cases[0].regression_id == regression.id
    assert detail.cases[0].passed is False
    assert detail.baseline_unavailable == "frozen_regression_selection"
    assert detail.members[0].results.id == selected.results[0].result_snapshot_id
    assert detail.members[0].labels.id
    assert captures == 2
    assert not commits
    assert original_capture() == before_read
    assert len(factory.calls) == 2

    with pytest.raises(ServiceFailure) as wrong_kind:
        DiagnosticService(runner).read_snapshot(started.group.group_id, selected.id)
    assert wrong_kind.value.error.reason == "diagnostic_snapshot_missing"

    stored = source.read(ResourceKey("check_snapshots", selected.id))
    assert stored is not None
    broken_result = selected.results[0].model_copy(update={"run_id": "foreign-run"})
    broken = selected.model_copy(update={"results": (broken_result,)})
    broken = broken.model_copy(update={"content_hash": content_hash(broken)})
    body = dump_record(broken)
    bad_stored = replace(stored, body=body, etag=bytes_hash(body))
    original_records = original_capture()
    corrupted_records = tuple(
        bad_stored if item.key == stored.key else item for item in original_records
    )
    monkeypatch.setattr(source, "capture_snapshot", lambda: corrupted_records)
    with pytest.raises(ServiceFailure) as corrupt_reference:
        checks.list_snapshots(started.group.group_id)
    assert corrupt_reference.value.error.reason == "group_snapshot_context_mismatch"
