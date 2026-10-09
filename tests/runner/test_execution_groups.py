import asyncio

import pytest

from deykit.application.dataset_support import safe_hash
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import DispatchOutcome, ExecutionSettings
from deykit.runner.planner import RunRequest


def request(cap=8):
    return RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="fixture",
        fixture_set_id="set",
        settings=ExecutionSettings(max_attempts=cap, concurrency=1),
    )


def test_group_orders_atomic_scope_replay_and_child_resume_rejected(setup):
    source, runner, factory, clock = setup(count=2)
    diagnostic = DiagnosticService(runner)
    result = asyncio.run(
        diagnostic.start(ChoiceOrderRequest(run=request()), operation_id="diagnose")
    )
    assert len(result.group.members) == 2
    assert result.group.attempts_used == 4
    assert len(factory.calls) == 4
    assert result.summary.independent_case_count == 2
    assert result.summary.expanded_result_count == 4
    assert factory.calls[0][1].body != factory.calls[2][1].body
    original = tuple(member.run_id for member in result.group.members)
    replay = asyncio.run(
        diagnostic.start(ChoiceOrderRequest(run=request()), operation_id="diagnose")
    )
    assert tuple(member.run_id for member in replay.group.members) == original
    assert len(factory.calls) == 4
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(runner.resume(original[0], operation_id="child", max_attempts=100))
    assert failure.value.error.reason == "resume_execution_group_required"
    assert len(factory.calls) == 4


def test_expanded_preflight_cap_writes_nothing(setup):
    source, runner, factory, _ = setup(count=2)
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            DiagnosticService(runner).start(
                ChoiceOrderRequest(run=request(cap=3)), operation_id="too-small"
            )
        )
    assert failure.value.error.reason == "group_initial_requests_exceed_cap"
    assert source.capture_snapshot() == before
    assert not factory.calls


def test_retry_uses_global_cap_and_resume_cannot_reset(setup):
    source, runner, factory, _ = setup(count=1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            retryable=True,
            error=ServiceError(code="provider_rejected", reason="rate_limit"),
        )
    ]
    service = DiagnosticService(runner)
    result = asyncio.run(
        service.start(ChoiceOrderRequest(run=request(cap=2)), operation_id="start")
    )
    assert len(factory.calls) == 2
    assert result.group.attempts_remaining == 0
    assert result.group.members[1].cases[0].status == "pending"
    resumed = asyncio.run(service.resume(result.group.group_id, operation_id="resume"))
    assert resumed.group.attempts_used == 2
    assert len(factory.calls) == 2


def test_save_regression_zero_calls_and_frozen_planner(setup):
    source, runner, factory, clock = setup(count=1)
    run = asyncio.run(runner.start(request(), operation_id="start"))
    service = RegressionService(source, clock, lambda: "reg-one")
    saved = service.add(
        RegressionAdd(
            run_id=run.run_id,
            case_id="case-00",
            acceptable_option_ids=("yes", "no"),
            reason="Keep this edge.",
        ),
        operation_id="save",
    )
    assert len(factory.calls) == 1
    plan = runner.planner.prepare(request().model_copy(update={"regression_ids": (saved.id,)}))
    assert plan.cases[0].input_source == '{"text":"Text 0","exact":9007199254740993}'
    assert plan.development_cases == ()
    assert plan.labels == ()
    assert service.remove(saved.id, decision_id="decision", operation_id="remove").removed
    assert service.list("decision") == ()
    assert source.list_ids("regressions") == (saved.id,)


def test_http_scoped_regression_rejects_cross_decision_before_identity_or_clock(setup, monkeypatch):
    source, runner, factory, clock = setup(count=1)
    run = asyncio.run(runner.start(request(), operation_id="origin"))
    identity_calls = []
    time_calls = []
    original_utc_now = clock.utc_now

    def utc_now():
        time_calls.append(True)
        return original_utc_now()

    clock.utc_now = utc_now
    service = RegressionService(source, clock, lambda: identity_calls.append(True) or "reg")
    body = RegressionAdd(
        run_id=run.run_id,
        case_id="case-00",
        acceptable_option_ids=("yes",),
        reason="Route-scoped oracle.",
    )
    before = source.capture_snapshot()

    with pytest.raises(ServiceFailure) as mismatch:
        service.add(body, operation_id="scoped-add", expected_decision_id="another-decision")

    assert mismatch.value.error.reason == "regression_decision_mismatch"
    assert source.capture_snapshot() == before
    assert identity_calls == [] and time_calls == [] and factory.calls

    saved = service.add(body, operation_id="scoped-add", expected_decision_id="decision")
    after = source.capture_snapshot()
    assert saved.decision_id == "decision"
    assert len(identity_calls) == len(time_calls) == 1

    with pytest.raises(ServiceFailure) as changed_scope:
        service.add(body, operation_id="scoped-add", expected_decision_id="another-decision")
    assert changed_scope.value.error.code == "conflict"
    assert source.capture_snapshot() == after

    def no_current_snapshot():
        raise AssertionError("receipt replay must not inspect the current run or labels")

    with monkeypatch.context() as patch:
        patch.setattr(source, "capture_snapshot", no_current_snapshot)
        replay = service.add(body, operation_id="scoped-add", expected_decision_id="decision")
        assert replay == saved
        assert len(identity_calls) == len(time_calls) == 1

    legacy_body = body.model_copy(update={"reason": "Legacy omitted scope."})
    receipt_hashes = []
    original_receipt = source.operation_receipt

    def record_receipt(operation_id, *, intent_hash):
        receipt_hashes.append(intent_hash)
        return original_receipt(operation_id, intent_hash=intent_hash)

    monkeypatch.setattr(source, "operation_receipt", record_receipt)
    service.add(legacy_body, operation_id="legacy-add")
    assert receipt_hashes[0] == safe_hash(
        {
            "command": "regression.add",
            "request": legacy_body.model_dump(mode="json"),
        }
    )


def test_frozen_check_after_case_deletion_and_unavailable_baseline(setup):
    from deykit.application.checks import CheckRequest, CheckService
    from deykit.application.evaluations import EvaluationService
    from deykit.contracts.ports import ResourceKey, SourceChange

    source, runner, factory, clock = setup(count=1)
    origin = asyncio.run(runner.start(request(), operation_id="origin"))
    reg = RegressionService(source, clock, lambda: "frozen-reg").add(
        RegressionAdd(
            run_id=origin.run_id,
            case_id="case-00",
            acceptable_option_ids=("no",),
            reason="Oracle no.",
        ),
        operation_id="save",
    )
    original_bytes = factory.calls[0][1].body
    key = ResourceKey("cases", "case-00", ("data",))
    source.commit("remove-case", (SourceChange(key, None, source.read(key).etag),))
    checks = CheckService(runner)
    result = asyncio.run(
        checks.start(
            CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="set"),
            operation_id="check",
        )
    )
    assert result.exit_code == 5 and result.expectation_failures == 1
    assert factory.calls[1][1].body == original_bytes
    member = result.group.members[0]
    evaluation = EvaluationService(source, clock).evaluate_saved(
        member.run_id, member.latest_result_snapshot_id, operation_id="evaluate"
    )
    baseline = evaluation.metrics["baseline"]
    assert baseline["unavailable_reason"] == "frozen_regression_selection"
    assert baseline["fit_support"] == 0
    assert baseline["accuracy"]["value"] is None
    RegressionService(source, clock).remove(
        reg.id, decision_id="decision", operation_id="remove-reg"
    )
    assert checks.read(result.group.group_id).expectation_failures == 1
    assert asyncio.run(
        checks.start(
            CheckRequest(decision_id="decision", mode="fixture", fixture_set_id="set"),
            operation_id="check",
        )
    ).group.replayed
    assert len(factory.calls) == 2


def test_active_group_replay_and_later_child_cancel_survives_group_boundary(setup):
    source, runner, factory, _ = setup(count=1)
    diagnostic = DiagnosticService(runner)
    observed = []

    async def callback(case_id, request_body):
        from conftest import answer

        if not observed:
            replay = await diagnostic.start(ChoiceOrderRequest(run=request()), operation_id="start")
            observed.append(replay)
            assert replay.group.replayed
            later = replay.group.members[1]
            runner.cancel(later.run_id, operation_id="cancel-later")
        return answer()

    factory.callback = callback
    result = asyncio.run(diagnostic.start(ChoiceOrderRequest(run=request()), operation_id="start"))
    assert len(factory.calls) == 1
    assert result.group.members[1].state == "cancelled"
    assert result.exit_code == 4


def test_group_unknown_is_retained_until_explicit_retry_and_cap_never_resets(setup):
    source, runner, factory, _ = setup(count=1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="run_incomplete", reason="timeout")
        )
    ]
    diagnostic = DiagnosticService(runner)
    result = asyncio.run(
        diagnostic.start(ChoiceOrderRequest(run=request(cap=3)), operation_id="start")
    )
    assert result.exit_code == 4 and len(factory.calls) == 2
    retained = asyncio.run(diagnostic.resume(result.group.group_id, operation_id="resume"))
    assert retained.exit_code == 4 and len(factory.calls) == 2
    retried = asyncio.run(
        diagnostic.resume(result.group.group_id, operation_id="retry", retry_unknown=True)
    )
    assert retried.exit_code == 0 and len(factory.calls) == 3
    assert retried.group.attempts_remaining == 0
    assert len(runner.repository.history(result.group.members[0].run_id).attempts) == 2


def test_group_deadline_not_reset_for_each_child(setup):
    source, runner, factory, clock = setup(count=1)

    async def callback(case_id, request_body):
        from conftest import answer

        clock.value += 3
        return answer()

    factory.callback = callback
    req = request().model_copy(
        update={"settings": ExecutionSettings(max_attempts=8, deadline_seconds=2, concurrency=1)}
    )
    result = asyncio.run(
        DiagnosticService(runner).start(ChoiceOrderRequest(run=req), operation_id="start")
    )
    assert len(factory.calls) == 1
    assert result.group.members[1].cases[0].status == "pending"
    assert result.exit_code == 4
