import asyncio

import pytest
from conftest import Clock
from test_execution import request

from deykit.application.demo import DemoService
from deykit.application.errors import ServiceFailure
from deykit.application.execution import ExecutionService
from deykit.contracts.codec import load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import DatasetSnapshot, ExecutionSettings, LabelSnapshot
from deykit.runner.backends import ProviderBackends
from deykit.runner.history import read_history
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource


def test_authored_sandbox_actual_factory_full_development_snapshot(tmp_path):
    clock = Clock()
    demo = DemoService(lambda path, create: FileProjectSource(path, create=create), clock).create(
        tmp_path / "Sandbox ü", operation_id="demo"
    )
    with FileProjectSource(demo.path) as source:
        service = ExecutionService(
            source, source, ProviderBackends(source, clock), clock, waiter=clock
        )
        selection = RunRequest(
            decision_id=demo.decision_id,
            dataset_id=demo.dataset_id,
            mode="fixture",
            fixture_set_id=demo.fixture_set_id,
            case_ids=("ex-001", "ex-011", "ex-012"),
        )
        before = source.capture_snapshot()
        preview = service.preview(selection)
        assert preview.initial_requests == 2 and len(preview.invalid_cases) == 1
        assert source.capture_snapshot() == before
        result = asyncio.run(service.start(selection, operation_id="start"))
        assert [case.status for case in result.cases] == [
            "valid",
            "input_invalid",
            "response_error",
        ]
        assert result.attempts_used == 2 and result.exit_code == 3
        manifest = read_history(source, result.run_id).manifest
        selected = load_record(
            DatasetSnapshot,
            source.read(ResourceKey("dataset_snapshots", manifest.dataset_snapshot_id)).body,
        )
        baseline = load_record(
            DatasetSnapshot,
            source.read(
                ResourceKey("dataset_snapshots", manifest.baseline_dataset_snapshot_id)
            ).body,
        )
        labels = load_record(
            LabelSnapshot,
            source.read(ResourceKey("label_snapshots", manifest.baseline_label_snapshot_id)).body,
        )
        assert len(selected.cases) == 3 and len(baseline.cases) > len(selected.cases)
        assert labels.labels and all(case.split == "development" for case in baseline.cases)
        assert service.show(result.run_id).segments[0].ended_at is not None
        from deykit.contracts.records import DecisionRevision

        revision = load_record(
            DecisionRevision,
            source.read(
                ResourceKey("revisions", manifest.decision_revision_id, (demo.decision_id,))
            ).body,
        )
        reordered = selection.model_copy(
            update={
                "case_ids": ("ex-001",),
                "option_order": tuple(
                    option.id for option in reversed(revision.definition.questions[0].options)
                ),
            }
        )
        unmatched = asyncio.run(service.start(reordered, operation_id="unmatched-order"))
        assert unmatched.cases[0].status == "response_error"
        assert unmatched.cases[0].error.code == "missing_fixture"
        assert unmatched.attempts_used == 1 and unmatched.mode == "fixture"


@pytest.mark.parametrize("callback", ["created", "progress"])
def test_callback_failure_safe_settlement_and_no_blind_dispatch(setup, callback, capsys):
    source, service, factory, _ = setup(4)

    def broken(_value):
        raise RuntimeError("PRIVATE_CALLBACK_SENTINEL")

    if callback == "created":
        with pytest.raises(ServiceFailure) as caught:
            asyncio.run(service.start(request(), operation_id="start", on_created=broken))
        assert "PRIVATE" not in str(caught.value)
        result = service.show(source.list_ids("runs")[0])
    else:
        result = asyncio.run(service.start(request(), operation_id="start", on_progress=broken))
    assert result.state == "interrupted" and not result.execution_active
    assert len(factory.calls) == (0 if callback == "created" else 2)
    assert "PRIVATE" not in capsys.readouterr().err
    resumed = asyncio.run(service.resume(result.run_id, operation_id="resume"))
    assert resumed.exit_code == 0 and len(factory.calls) == 4


def test_deadline_rechecked_after_durable_reservation(setup):
    _, service, factory, clock = setup(1)

    def delay(stage, _attempt):
        if stage == "after_intent":
            clock.value += 10

    service.scheduler.hook = delay
    result = asyncio.run(
        service.start(request(settings=ExecutionSettings(deadline_seconds=5)), operation_id="start")
    )
    assert result.state == "budget_exhausted" and result.attempts_used == 1
    assert result.cases[0].status == "pending" and factory.calls == []


def test_terminal_cancel_and_project_owner_do_not_change_completed_status(setup):
    _, service, _, _ = setup(1)
    first = asyncio.run(service.start(request(), operation_id="first"))
    cancelled = service.cancel(first.run_id, operation_id="late-cancel")
    assert cancelled.state == "completed" and cancelled.exit_code == 0
    observed = []
    asyncio.run(
        service.start(
            request(),
            operation_id="second",
            on_created=lambda _: observed.append(service.show(first.run_id)),
        )
    )
    assert not observed[0].execution_active
    page = service.list(limit=1)
    assert page.total == 2 and len(page.items) == 1 and page.next_cursor is not None
    assert service.list(cursor=page.next_cursor).items[0].run_id != page.items[0].run_id


@pytest.mark.parametrize("value", [None, {"bad": "PRIVATE"}, 123])
def test_untrusted_request_shapes_are_safe_zero_write(setup, value, capsys):
    source, service, factory, _ = setup(1)
    before = source.capture_snapshot()
    with pytest.raises(ServiceFailure):
        service.preview(value)
    assert source.capture_snapshot() == before and factory.calls == []
    assert not capsys.readouterr().err


def test_constructed_nested_request_rejected_before_serializer(setup, capsys):
    source, service, factory, _ = setup(1)
    bad = request().model_copy(update={"settings": ("PRIVATE_SETTINGS_SENTINEL",)})
    with pytest.raises(ServiceFailure):
        service.preview(bad)
    assert not capsys.readouterr().err and not source.list_ids("runs") and not factory.calls


def test_parent_task_cancellation_keeps_owner_until_inflight_settles(setup):
    from conftest import answer

    source, service, factory, _ = setup(2)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def transport(_case, _request):
            entered.set()
            await release.wait()
            return answer()

        factory.callback = transport
        task = asyncio.create_task(
            service.start(request(settings=ExecutionSettings(concurrency=1)), operation_id="start")
        )
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert source.execution_active() and not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    result = service.show(source.list_ids("runs")[0])
    assert result.state == "interrupted" and not result.execution_active
    assert [case.status for case in result.cases] == ["valid", "pending"]
    assert len(factory.calls) == 1


def test_malformed_transport_outcome_never_serializes_private_object(setup, capsys):
    from deykit.contracts.records import DispatchOutcome

    _, service, factory, _ = setup(1)
    factory.responses["case-00"] = [
        DispatchOutcome.model_construct(state="known", answer=("PRIVATE_TRANSPORT_SENTINEL",))
    ]
    result = asyncio.run(service.start(request(), operation_id="start"))
    assert result.cases[0].status == "unknown" and len(factory.calls) == 1
    assert not capsys.readouterr().err


def test_active_resume_replay_acknowledges_original_segment_without_dispatch(setup):
    from conftest import answer

    source, service, factory, _ = setup(1)
    stopped = asyncio.run(
        service.start(
            request(),
            operation_id="start",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )
    acknowledged = []

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def transport(_case, _request):
            entered.set()
            await release.wait()
            return answer()

        def resumed(value):
            history = read_history(source, value.run_id)
            assert history.segments[-1].id == value.segment_id
            assert not service.repository.cancelled(history, history.segments[-1])
            assert not factory.calls
            acknowledged.append(value)

        factory.callback = transport
        task = asyncio.create_task(
            service.resume(stopped.run_id, operation_id="resume", on_resumed=resumed)
        )
        await entered.wait()
        replays = []
        replayed = await service.resume(
            stopped.run_id, operation_id="resume", on_resumed=replays.append
        )
        assert replayed.replayed and replayed.execution_active
        assert replays[0].replayed and replays[0].segment_id == acknowledged[0].segment_id
        assert len(factory.calls) == 1
        release.set()
        return await task

    result = asyncio.run(scenario())
    assert result.exit_code == 0 and len(result.segment_ids) == 2


def test_resumed_callback_failure_leaves_durable_segment_without_dispatch(setup):
    source, service, factory, _ = setup(1)
    stopped = asyncio.run(
        service.start(
            request(),
            operation_id="start",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )

    def fail(_event):
        raise RuntimeError("PRIVATE_RESUMED_SENTINEL")

    with pytest.raises(ServiceFailure) as caught:
        asyncio.run(service.resume(stopped.run_id, operation_id="resume", on_resumed=fail))
    assert caught.value.error.reason == "resumed_callback_failed" and not factory.calls
    history = read_history(source, stopped.run_id)
    assert history.state == "interrupted" and len(history.segments) == 2
    replay = asyncio.run(service.resume(stopped.run_id, operation_id="resume"))
    assert replay.replayed and not factory.calls


def test_frozen_profile_hash_mismatch_fails_before_resume_dispatch(setup):
    from dataclasses import replace

    from deykit.contracts.codec import dump_record
    from deykit.contracts.records import RunManifest

    source, service, factory, _ = setup(1)
    stopped = asyncio.run(
        service.start(
            request(),
            operation_id="start",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )
    original = source.capture_snapshot()
    changed = []
    for stored in original:
        if stored.key.collection == "runs":
            manifest = load_record(RunManifest, stored.body)
            stored = replace(
                stored,
                body=dump_record(
                    manifest.model_copy(
                        update={
                            "provider_config_hash": "0" * 64,
                        }
                    )
                ),
            )
        changed.append(stored)

    class TamperedCapture:
        def capture_snapshot(self):
            return tuple(changed)

    with pytest.raises(ServiceFailure) as caught:
        read_history(TamperedCapture(), stopped.run_id)
    assert caught.value.error.reason == "invalid_frozen_run_context" and not factory.calls


def test_adapter_capability_preflight_rejects_options_even_without_valid_cases(setup):
    from unittest.mock import Mock

    from deykit.contracts.records import ChoiceDefinition, ChoiceOption, ChoiceQuestion
    from deykit.runner.backends import LiveBackend

    _, _, _, _ = setup(1, invalid=(0,))
    provider = Mock()
    definition = ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose.",
                options=tuple(
                    ChoiceOption(id=f"option-{index}", name=f"Option {index}")
                    for index in range(256)
                ),
            ),
        ),
    )
    result = LiveBackend(provider).preflight("decision", "data", definition)
    assert result.reason == "unsupported_option_count"
    provider.preflight.assert_not_called()


def test_live_backend_uses_frozen_reference_credentials_without_network(setup, monkeypatch):
    from deykit.contracts.records import ProviderProfile
    from deykit.providers.credentials import Credentials
    from deykit.runner import backends

    source, _, _, clock = setup(1)
    observed = []
    profile = ProviderProfile(
        id="live",
        adapter="jev",
        requested_model="jev-latest",
        destination="https://api.typesafe.ai/v1/systemone",
        credential_ref="env:OFFLINE_SENTINEL",
    )

    def credentials(value):
        observed.append(value)
        return Credentials({"OFFLINE_SENTINEL": "PRIVATE_OFFLINE_CREDENTIAL"})

    monkeypatch.setattr(backends, "credentials_for", credentials)
    backend = ProviderBackends(source, clock).resolve(profile, None)
    assert backend.preflight("decision", "data") is None and observed == [profile]
