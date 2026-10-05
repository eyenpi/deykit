"""Post-settlement CLI evaluation retains each caller action's frozen boundary."""

import asyncio
import json

import pytest
from typer.testing import CliRunner

from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService, evaluation_hash
from deykit.application.labels import LabelService
from deykit.cli.commands import execution
from deykit.cli.main import app
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DispatchOutcome
from deykit.runner.planner import RunRequest

cli = CliRunner()


def invoke(source, *args):
    return cli.invoke(app, ["--json", "--project", str(source.root), *args])


def start_args():
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
        "--operation-id",
        "start",
    )


def test_execution_action_replay_retains_evaluation_after_resume_and_label_edit(setup, monkeypatch):
    source, runner, factory, clock = setup(1)
    monkeypatch.setattr(execution, "service", lambda _: runner)
    factory.responses = {
        "case-00": [
            DispatchOutcome(
                state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
            )
        ]
    }
    first = invoke(source, *start_args())
    assert first.exit_code == 4, first.output
    original = json.loads(first.stdout)["data"]
    run_id = original["run"]["run_id"]
    evaluations = EvaluationService(source, clock)
    old = evaluations.read(original["evaluation_id"])
    assert old.metrics["summary"]["status_counts"]["unknown"] == 1
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="human",
        operation_id="label",
    )
    resume = ("runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume")
    second = invoke(source, *resume)
    assert second.exit_code == 0, second.output
    fresh = json.loads(second.stdout)["data"]
    assert fresh["evaluation_id"] != original["evaluation_id"]
    assert fresh["evaluation_result_snapshot_id"] != original["evaluation_result_snapshot_id"]
    new = evaluations.read(fresh["evaluation_id"])
    assert new.metrics["summary"]["status_counts"]["valid"] == 1
    assert new.metrics["summary"]["set_accuracy"]["value"] is None  # original frozen labels
    replay = invoke(source, *start_args())
    assert replay.exit_code == 0, replay.output
    repeated = json.loads(replay.stdout)["data"]
    assert repeated["evaluation_id"] == original["evaluation_id"]
    assert repeated["evaluation_result_snapshot_id"] == original["evaluation_result_snapshot_id"]
    assert repeated["evaluation_replayed"]
    again = invoke(source, *resume)
    assert json.loads(again.stdout)["data"]["evaluation_id"] == fresh["evaluation_id"]
    assert evaluations.read(old.record.id).metrics == old.metrics
    assert len(factory.calls) == 2


@pytest.mark.parametrize("state,expected", [("known", 3), ("unknown", 4), ("valid", 1)])
@pytest.mark.parametrize("unsafe", [False, True])
def test_evaluation_failure_retains_run_identity_and_execution_exit(
    setup, monkeypatch, state, expected, unsafe
):
    source, runner, factory, _ = setup(1)
    monkeypatch.setattr(execution, "service", lambda _: runner)
    if state != "valid":
        factory.responses = {
            "case-00": [
                DispatchOutcome(
                    state=state, error=ServiceError(code="provider_rejected", reason="test_failure")
                )
            ]
        }

    def fail(*args, **kwargs):
        if unsafe:
            raise RuntimeError("PRIVATE_EVALUATION_SENTINEL")
        raise ServiceFailure(
            ServiceError(code="internal_error", reason="evaluation_storage_failed")
        )

    monkeypatch.setattr(EvaluationService, "evaluate_execution", fail)
    result = invoke(source, *start_args())
    assert result.exit_code == expected, result.output
    payload = json.loads(result.stdout)
    run_id = source.list_ids("runs")[0]
    if expected in (3, 4):
        assert payload["data"]["run"]["run_id"] == run_id
        assert payload["data"]["evaluation_error"]["resource_id"] == run_id
        assert "evaluation_id" not in payload["data"]
        assert payload["warnings"][0]["resource_id"] == run_id
    else:
        assert payload["error"]["resource_id"] == run_id
    assert "PRIVATE_EVALUATION_SENTINEL" not in result.output
    assert not source.list_ids("evaluations") and len(factory.calls) == 1
    invoke(source, *start_args())
    assert len(factory.calls) == 1


def test_duplicate_execution_associations_are_incompatible(setup):
    source, runner, _, clock = setup(1)
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    evaluations = EvaluationService(source, clock)
    first = evaluations.evaluate_execution(
        run.run_id, run.latest_result_snapshot_id, execution_operation_id="start"
    )
    duplicate = first.record.model_copy(update={"id": "duplicate"})
    assert evaluation_hash(duplicate) == duplicate.content_hash
    source.commit(
        "duplicate",
        (SourceChange(ResourceKey("evaluations", "duplicate"), dump_record(duplicate), None),),
    )
    with pytest.raises(ServiceFailure) as raised:
        evaluations.evaluate_execution(
            run.run_id, run.latest_result_snapshot_id, execution_operation_id="start"
        )
    assert raised.value.error.reason == "execution_evaluation_conflict"


def test_active_action_replay_defers_new_evaluation_but_retains_existing_binding(setup):
    source, runner, factory, _ = setup(1)
    from conftest import answer

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        call_count = 0

        async def dispatch(case_id, request):
            nonlocal call_count
            call_count += 1
            entered.set()
            await release.wait()
            if call_count == 1:
                return DispatchOutcome(
                    state="unknown", error=ServiceError(code="provider_rejected", reason="timeout")
                )
            return answer()

        factory.callback = dispatch
        request = RunRequest(
            decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
        )
        first_task = asyncio.create_task(runner.start(request, operation_id="start"))
        await entered.wait()
        active = await runner.start(request, operation_id="start")
        assert active.execution_active
        pending = execution._evaluated(source, active, "start")
        assert pending.data["evaluation_pending"] is True
        assert "evaluation_id" not in pending.data
        assert not source.list_ids("evaluations")
        release.set()
        first = await first_task
        assert not first.execution_active
        original = execution._evaluated(source, first, "start")
        assert original.data["evaluation_id"]
        entered.clear()
        release.clear()
        resumed_task = asyncio.create_task(
            runner.resume(first.run_id, operation_id="resume", retry_unknown=True)
        )
        await entered.wait()
        old_action = await runner.start(request, operation_id="start")
        assert old_action.execution_active
        retained = execution._evaluated(source, old_action, "start")
        assert retained.data["evaluation_id"] == original.data["evaluation_id"]
        active_resume = await runner.resume(first.run_id, operation_id="resume", retry_unknown=True)
        assert active_resume.execution_active
        assert execution._evaluated(source, active_resume, "resume").data["evaluation_pending"]
        assert len(source.list_ids("evaluations")) == 1
        release.set()
        resumed = await resumed_task
        final = execution._evaluated(source, resumed, "resume")
        assert final.data["evaluation_id"] != original.data["evaluation_id"]
        assert len(factory.calls) == 2

    asyncio.run(exercise())
