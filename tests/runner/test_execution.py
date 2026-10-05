import asyncio

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.records import DispatchOutcome, ExecutionSettings
from deykit.runner.planner import RunRequest


def request(**changes):
    return RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set", **changes
    )


def test_a17_visible_invalid_input_dry_run_and_exact_initial_requests(setup):
    source, service, factory, _ = setup(12, invalid=(2,))
    before = source.capture_snapshot()
    preview = service.preview(request())
    assert preview.initial_requests == 11 and len(preview.invalid_cases) == 1
    assert factory.calls == [] and source.capture_snapshot() == before
    result = asyncio.run(service.start(request(), operation_id="start"))
    assert len(factory.calls) == 11 and result.attempts_used == 11
    assert [case.status for case in result.cases].count("valid") == 11
    assert [case.status for case in result.cases].count("input_invalid") == 1
    assert result.exit_code == 3
    assert all(b"9007199254740993" not in wire.body for _, wire, _ in factory.calls)
    assert service.show(result.run_id).state == "completed_with_errors"


@pytest.mark.parametrize("failure", ["cap", "credential"])
def test_a18_global_preflight_has_zero_dispatch_and_no_run(setup, failure):
    source, service, factory, _ = setup()
    if failure == "credential":
        factory.error = ServiceError(code="preflight_failed", reason="credential_unavailable")
    options = request(settings=ExecutionSettings(max_attempts=2 if failure == "cap" else 100))
    with pytest.raises(ServiceFailure) as raised:
        asyncio.run(service.start(options, operation_id="start"))
    assert raised.value.error.code == "preflight_failed"
    assert factory.calls == [] and source.list_ids("runs") == ()


def test_a19_atomic_cap_with_pending_request_and_documented_retry(setup):
    _, service, factory, _ = setup()
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            error=ServiceError(code="provider_rejected", reason="rate_limit"),
            retryable=True,
        )
    ]
    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=3, concurrency=2)), operation_id="start"
        )
    )
    assert result.attempts_used == 3 and len(factory.calls) == 3
    assert [case for case, _, _ in factory.calls] == ["case-00", "case-01", "case-02"]
    assert (
        result.state == "budget_exhausted"
        and result.attempts_remaining == 0
        and result.exit_code == 4
    )


def test_documented_retry_once_and_unknown_never_automatic(setup):
    _, service, factory, _ = setup(2)
    limited = DispatchOutcome(
        state="known",
        error=ServiceError(code="provider_rejected", reason="overloaded"),
        retryable=True,
    )
    factory.responses = {
        "case-00": [limited, limited],
        "case-01": [
            DispatchOutcome(
                state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
            )
        ],
    }
    result = asyncio.run(service.start(request(), operation_id="start"))
    assert len(factory.calls) == 3 and result.attempts_used == 3
    assert [attempt.kind for attempt in result.attempts].count("rate_retry") == 1
    assert result.exit_code == 4
    preview = service.preview_resume(result.run_id)
    assert preview.planned_case_ids == ()
    assert service.preview_resume(result.run_id, retry_unknown=True).planned_case_ids == (
        "case-01",
    )


def test_a26_semantic_start_replay_after_unknown_never_redispatches(setup):
    _, service, factory, _ = setup(1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="disconnect")
        )
    ]
    first = asyncio.run(service.start(request(), operation_id="same"))
    repeated = asyncio.run(service.start(request(), operation_id="same"))
    assert repeated.run_id == first.run_id and repeated.replayed and len(factory.calls) == 1
    with pytest.raises(ServiceFailure) as raised:
        asyncio.run(
            service.start(request(settings=ExecutionSettings(max_attempts=50)), operation_id="same")
        )
    assert raised.value.error.reason == "operation_id_conflict"


def test_cancel_from_created_callback_is_not_acknowledged_as_old_request(setup):
    _, service, factory, _ = setup()
    result = asyncio.run(
        service.start(
            request(),
            operation_id="start",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )
    assert result.state == "cancelled" and result.attempts_used == 0 and factory.calls == []
    resumed = asyncio.run(service.resume(result.run_id, operation_id="resume"))
    assert resumed.state == "completed" and resumed.attempts_used == 3
    service.cancel(result.run_id, operation_id="cancel")
    assert len(factory.calls) == 3
