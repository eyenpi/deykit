import asyncio

import pytest
from conftest import answer
from test_execution import request

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, DispatchOutcome, ExecutionSettings
from deykit.runner.history import read_history


def limited(delay=0):
    return DispatchOutcome(
        state="known",
        error=ServiceError(code="provider_rejected", reason="rate_limit"),
        retryable=True,
        retry_after_seconds=delay,
    )


@pytest.mark.parametrize("ending", ["cancel", "deadline"])
def test_a20_interruptible_backoff_prevents_retry(setup, ending):
    _, service, factory, clock = setup(1)
    factory.responses["case-00"] = [limited(30)]

    def progress(value):
        if ending == "cancel":
            service.cancel(value.run_id, operation_id="cancel")
        else:
            clock.value = 2

    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(deadline_seconds=1)),
            operation_id="start",
            on_progress=progress,
        )
    )
    assert len(factory.calls) == 1 and result.attempts_used == 1
    assert result.state == ("cancelled" if ending == "cancel" else "budget_exhausted")
    assert service.preview_resume(result.run_id).planned_case_ids == ("case-00",)


@pytest.mark.parametrize(
    "code,reason", [("provider_auth", None), ("provider_rejected", "invalid_payload")]
)
def test_a21_provider_wide_failure_stops_new_calls_and_resume(setup, code, reason):
    _, service, factory, _ = setup(4)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known", error=ServiceError(code=code, reason=reason), provider_wide=True
        )
    ]
    result = asyncio.run(service.start(request(), operation_id="start"))
    assert len(factory.calls) == 1
    assert result.exit_code == 4 and any(item.status == "pending" for item in result.cases)
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(service.resume(result.run_id, operation_id="resume"))
    assert failure.value.error.reason == "terminal_provider_failure_requires_new_run"


def test_a22_cancel_settles_two_inflight_and_preserves_pending(setup):
    _, service, factory, _ = setup(5)

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        run_id = []

        async def transport(case_id, wire):
            if len(factory.calls) == 2:
                started.set()
            await release.wait()
            return answer()

        factory.callback = transport
        task = asyncio.create_task(
            service.start(
                request(),
                operation_id="start",
                on_created=lambda event: run_id.append(event.run_id),
            )
        )
        await started.wait()
        active = service.show(run_id[0])
        assert active.execution_active and active.attempts_used == 2
        service.cancel(run_id[0], operation_id="cancel")
        release.set()
        return await task

    result = asyncio.run(scenario())
    assert len(factory.calls) == 2 and result.state == "cancelled"
    assert [item.status for item in result.cases] == [
        "valid",
        "valid",
        "pending",
        "pending",
        "pending",
    ]


def test_a24_recovery_counts_and_explicit_unknown_retry_preserve_snapshots(setup):
    source, service, factory, _ = setup(12, invalid=(8,))
    factory.responses["case-09"] = [
        DispatchOutcome(
            state="known", error=ServiceError(code="response_invalid", reason="invalid_choice")
        )
    ]
    factory.responses["case-10"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
        )
    ]

    def cancel_after_ten(value):
        if value.attempts_used == 10:
            service.cancel(value.run_id, operation_id="cancel")

    result = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(concurrency=1)),
            operation_id="start",
            on_progress=cancel_after_ten,
        )
    )
    counts = {
        status: sum(case.status == status for case in result.cases)
        for status in ("valid", "input_invalid", "response_error", "unknown", "pending")
    }
    assert counts == {
        "valid": 8,
        "input_invalid": 1,
        "response_error": 1,
        "unknown": 1,
        "pending": 1,
    }
    assert result.attempts_used == 10 and result.attempts_remaining == 90
    assert service.preview_resume(result.run_id).planned_case_ids == ("case-11",)
    assert service.preview_resume(result.run_id, retry_unknown=True).planned_case_ids == (
        "case-10",
        "case-11",
    )
    key = ResourceKey("result_snapshots", result.latest_result_snapshot_id)
    old = source.read(key).body
    resumed = asyncio.run(service.resume(result.run_id, operation_id="resume"))
    assert resumed.attempts_used == 11 and len(factory.calls) == 11
    explicit = asyncio.run(
        service.resume(result.run_id, operation_id="retry-unknown", retry_unknown=True)
    )
    assert explicit.attempts_used == 12 and len(factory.calls) == 12
    assert source.read(key).body == old
    history = read_history(source, result.run_id)
    assert len(history.case_attempts("case-10")) == 2
    assert history.case_attempts("case-10")[-1].kind == "unknown_retry"


def test_lifetime_extension_is_append_only_and_resume_replays(setup):
    source, service, factory, _ = setup(1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="disconnect")
        )
    ]
    first = asyncio.run(
        service.start(
            request(settings=ExecutionSettings(max_attempts=1, deadline_seconds=5)),
            operation_id="start",
        )
    )
    resumed = asyncio.run(
        service.resume(first.run_id, operation_id="resume", retry_unknown=True, max_attempts=2)
    )
    assert resumed.attempts_used == 2 and resumed.attempt_limit == 2 and resumed.exit_code == 0
    again = asyncio.run(
        service.resume(first.run_id, operation_id="resume", retry_unknown=True, max_attempts=2)
    )
    assert again.replayed and len(factory.calls) == 2
    history = read_history(source, first.run_id)
    assert history.manifest.settings.max_attempts == 1
    assert [item.max_attempts for item in history.controls] == [2]
    assert all(
        (
            __import__("datetime").datetime.fromisoformat(
                segment.deadline_at.replace("Z", "+00:00")
            )
            - __import__("datetime").datetime.fromisoformat(
                segment.started_at.replace("Z", "+00:00")
            )
        ).total_seconds()
        == 5
        for segment in history.segments
    )
    with pytest.raises(ServiceFailure):
        asyncio.run(service.resume(first.run_id, operation_id="lower", max_attempts=1))


def test_resume_uses_saved_bytes_profile_and_definition_without_compile(setup):
    source, service, factory, _ = setup(1)
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="unknown", error=ServiceError(code="provider_rejected", reason="disconnect")
        )
    ]
    first = asyncio.run(service.start(request(), operation_id="start"))
    original = factory.calls[0][1]
    stored = source.read(ResourceKey("cases", "case-00", ("data",)))
    case = load_record(CaseRecord, stored.body)
    source.commit(
        "edit",
        (
            SourceChange(
                stored.key,
                dump_record(case.model_copy(update={"input_source": '{"text":"changed"}'})),
                stored.etag,
            ),
        ),
    )
    factory.profile_value = factory.profile_value.model_copy(
        update={"requested_model": "different"}
    )

    class ForbiddenCompiler:
        def compile(self, *args):
            raise AssertionError("Resume recompiled")

    factory.compiler = ForbiddenCompiler()
    second = asyncio.run(service.resume(first.run_id, operation_id="resume", retry_unknown=True))
    assert second.exit_code == 0 and factory.calls[1][1] == original
    assert factory.resolved_profile.requested_model == "authored-v1"


def test_received_but_unpersisted_stops_new_dispatch_and_recovers_unknown(setup):
    source, service, factory, _ = setup(3)

    def hook(stage, attempt):
        if stage == "after_received":

            def fail_prepared(checkpoint):
                if checkpoint == "prepared":
                    raise OSError("PRIVATE_INPUT_SENTINEL")

            source._hook = fail_prepared

    service.scheduler.hook = hook
    with pytest.raises(ServiceFailure) as failure:
        asyncio.run(
            service.start(request(settings=ExecutionSettings(concurrency=1)), operation_id="start")
        )
    assert failure.value.error.reason == "persistence_failed" and "PRIVATE_INPUT" not in str(
        failure.value
    )
    assert len(factory.calls) == 1
    source._hook = lambda stage: None
    run_id = source.list_ids("runs")[0]
    recovered = service.show(run_id)
    assert recovered.attempts_used == 1
    assert [item.status for item in recovered.cases] == ["unknown", "pending", "pending"]
