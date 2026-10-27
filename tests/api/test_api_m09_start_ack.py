"""Actual ASGI regression for a frozen standalone run without durable readiness."""

import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from test_m09_http_guards import (
    _app,
    _register_project,
    _run_request,
    _seed_one_case,
    _session,
)

from deykit.api.dependencies import ApiProjectSource
from deykit.api.supervisor import ExecutionSupervisor
from deykit.application.execution_groups import GroupExecutionService
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.contracts.execution_groups import ExecutionGroup, ExecutionGroupSegment
from deykit.providers.fixtures import FixtureCaseTransport, FixtureTransportFactory
from deykit.runner.backends import ProviderBackends
from deykit.runner.group_models import GroupProgress
from deykit.runner.planner import Planner


class _CountedProbe:
    def __init__(self, probe: Callable[[], bool]) -> None:
        self.probe = probe
        self.calls = 0

    def __call__(self) -> bool:
        self.calls += 1
        return self.probe()


def test_http_empty_check_scope_is_preflight_failure_without_dispatch(
    tmp_path: Path, monkeypatch
) -> None:
    context = _app(tmp_path)
    calls = {
        "profile": 0,
        "resolve": 0,
        "legacy_resolve": 0,
        "for_case": 0,
        "dispatch": 0,
        "planner_prepare": 0,
        "planner_prepare_many": 0,
    }
    original_profile = ProviderBackends.profile_captured
    original_resolve = ProviderBackends.resolve_captured
    original_legacy_resolve = ProviderBackends.resolve
    original_for_case = FixtureTransportFactory.for_case
    original_dispatch = FixtureCaseTransport.dispatch
    original_prepare = Planner.prepare
    original_prepare_many = Planner.prepare_many

    def profile(*args: Any, **kwargs: Any) -> Any:
        calls["profile"] += 1
        return original_profile(*args, **kwargs)

    def resolve(*args: Any, **kwargs: Any) -> Any:
        calls["resolve"] += 1
        return original_resolve(*args, **kwargs)

    def legacy_resolve(*args: Any, **kwargs: Any) -> Any:
        calls["legacy_resolve"] += 1
        return original_legacy_resolve(*args, **kwargs)

    def for_case(*args: Any, **kwargs: Any) -> Any:
        calls["for_case"] += 1
        return original_for_case(*args, **kwargs)

    async def dispatch(*args: Any, **kwargs: Any) -> Any:
        calls["dispatch"] += 1
        return await original_dispatch(*args, **kwargs)

    def prepare(*args: Any, **kwargs: Any) -> Any:
        calls["planner_prepare"] += 1
        return original_prepare(*args, **kwargs)

    def prepare_many(*args: Any, **kwargs: Any) -> Any:
        calls["planner_prepare_many"] += 1
        return original_prepare_many(*args, **kwargs)

    monkeypatch.setattr(ProviderBackends, "profile_captured", profile)
    monkeypatch.setattr(ProviderBackends, "resolve_captured", resolve)
    monkeypatch.setattr(ProviderBackends, "resolve", legacy_resolve)
    monkeypatch.setattr(FixtureTransportFactory, "for_case", for_case)
    monkeypatch.setattr(FixtureCaseTransport, "dispatch", dispatch)
    monkeypatch.setattr(Planner, "prepare", prepare)
    monkeypatch.setattr(Planner, "prepare_many", prepare_many)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary),
                base_url=context.origin,
            ) as client:
                headers = await _session(client, context.origin)
                registration_id = await _register_project(
                    client, headers, tmp_path / "empty-check-scope", "Empty Check Scope"
                )
                source: ApiProjectSource = context.api.state.project_registry.require(
                    registration_id
                ).source
                _seed_one_case(source, context.dependencies)
                before = source.capture_snapshot()
                base = f"/api/v1/projects/{registration_id}"
                response = await client.post(
                    f"{base}/checks/preview",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "request": {
                            "decision_id": "decision",
                            "mode": "fixture",
                            "fixture_set_id": "fixture-set",
                            "regression_ids": [],
                            "settings": {"max_attempts": 1, "concurrency": 1},
                        },
                    },
                )
                assert response.status_code == 422
                error = response.json()["error"]
                assert error["code"] == "preflight_failed"
                assert error["reason"] == "empty_regression_scope"
                assert source.capture_snapshot() == before
                assert source.list_ids("execution_groups") == ()
                assert source.list_ids("runs") == ()
                assert calls == {
                    "profile": 0,
                    "resolve": 0,
                    "legacy_resolve": 0,
                    "for_case": 0,
                    "dispatch": 0,
                    "planner_prepare": 0,
                    "planner_prepare_many": 0,
                }

    asyncio.run(exercise())


def test_http_standalone_incomplete_start_and_original_replay_never_return_202(
    tmp_path: Path, monkeypatch
) -> None:
    context = _app(tmp_path)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary), base_url=context.origin
            ) as client:
                headers = await _session(client, context.origin)
                registration_id = await _register_project(
                    client, headers, tmp_path / "incomplete-project", "Incomplete Project"
                )
                source: ApiProjectSource = context.api.state.project_registry.require(
                    registration_id
                ).source
                _seed_one_case(source, context.dependencies)
                base = f"/api/v1/projects/{registration_id}"
                request = _run_request()
                preview = await client.post(
                    f"{base}/runs/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": request},
                )
                assert preview.status_code == 200, preview.text
                start = {
                    "schema_version": 1,
                    "operation_id": "http-incomplete-start",
                    "expected_review_context_hash": preview.json()["data"]["review_context_hash"],
                    "request": request,
                }
                commit = source.commit

                def fail_ready(operation_id, changes, *, intent_hash=None):
                    if any(
                        change.key.collection == "run_events"
                        and change.body is not None
                        and b"segment_ready" in change.body
                        for change in changes
                    ):
                        raise OSError("simulated ready commit failure")
                    return commit(operation_id, changes, intent_hash=intent_hash)

                monkeypatch.setattr(source, "commit", fail_ready)
                first = await client.post(f"{base}/runs", headers=headers, json=start)
                assert first.status_code == 409, first.text
                before_replay = source.capture_snapshot()
                active_probe = _CountedProbe(source.execution_active)
                backend_calls = 0
                execution_active = source.execution_active
                original_resolve = ProviderBackends.resolve
                original_resolve_captured = ProviderBackends.resolve_captured

                def reject_backend_resolve(*args: object, **kwargs: object) -> None:
                    del args, kwargs
                    nonlocal backend_calls
                    backend_calls += 1
                    raise AssertionError("receipt replay resolved the current backend")

                monkeypatch.setattr(source, "execution_active", active_probe)
                monkeypatch.setattr(ProviderBackends, "resolve", reject_backend_resolve)
                monkeypatch.setattr(ProviderBackends, "resolve_captured", reject_backend_resolve)
                replay = await client.post(f"{base}/runs", headers=headers, json=start)

                assert replay.status_code == 409, replay.text
                assert first.json()["error"]["reason"] == "start_acknowledgement_incomplete"
                assert replay.json()["error"]["reason"] == "start_acknowledgement_incomplete"
                assert first.json()["error"]["resource_id"] == replay.json()["error"]["resource_id"]
                assert source.capture_snapshot() == before_replay
                assert active_probe.calls == 0 and backend_calls == 0
                monkeypatch.setattr(source, "execution_active", execution_active)
                monkeypatch.setattr(ProviderBackends, "resolve", original_resolve)
                monkeypatch.setattr(ProviderBackends, "resolve_captured", original_resolve_captured)

    asyncio.run(exercise())


def test_http_group_incomplete_receipt_replay_is_409_for_both_group_kinds(
    tmp_path: Path, monkeypatch
) -> None:
    context = _app(tmp_path)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary, raise_app_exceptions=False),
                base_url=context.origin,
            ) as client:
                headers = await _session(client, context.origin)
                registration_id = await _register_project(
                    client, headers, tmp_path / "incomplete-groups", "Incomplete Groups"
                )
                source: ApiProjectSource = context.api.state.project_registry.require(
                    registration_id
                ).source
                _seed_one_case(source, context.dependencies)
                base = f"/api/v1/projects/{registration_id}"
                run_request = _run_request()
                kinds: list[tuple[str, dict[str, object], str]] = []

                # A real completed fixture run supplies an admitted, immutable regression source.
                baseline_preview = await client.post(
                    f"{base}/runs/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": run_request},
                )
                assert baseline_preview.status_code == 200, baseline_preview.text
                baseline_start = await client.post(
                    f"{base}/runs",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "group-test-baseline",
                        "expected_review_context_hash": baseline_preview.json()["data"][
                            "review_context_hash"
                        ],
                        "request": run_request,
                    },
                )
                assert baseline_start.status_code == 202, baseline_start.text
                run_id = baseline_start.json()["data"]["run_id"]
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    progress = await client.get(f"{base}/runs/{run_id}", headers=headers)
                    if (
                        progress.status_code == 409
                        and progress.json().get("error", {}).get("reason") == "source_busy"
                    ):
                        await asyncio.sleep(0.01)
                        continue
                    assert progress.status_code == 200, progress.text
                    if progress.json()["data"]["latest_result_snapshot_id"]:
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("fixture baseline did not settle")
                RegressionService(
                    source, context.dependencies.clock, context.dependencies.id_factory
                ).add(
                    RegressionAdd(
                        run_id=run_id,
                        case_id="case",
                        acceptable_option_ids=("yes",),
                        reason="authored HTTP group regression",
                        provenance="authored_fixture",
                    ),
                    operation_id="group-test-regression",
                    expected_decision_id="decision",
                )

                choice_request: dict[str, object] = {
                    "run": run_request,
                    "orders": 1,
                    "seed": "0",
                }
                choice_preview = await client.post(
                    f"{base}/diagnostics/choice-order/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": choice_request},
                )
                assert choice_preview.status_code == 200, choice_preview.text
                kinds.append(
                    (
                        "/diagnostics/choice-order",
                        choice_request,
                        choice_preview.json()["data"]["review_context_hash"],
                    )
                )

                check_request: dict[str, object] = {
                    "decision_id": "decision",
                    "mode": "fixture",
                    "fixture_set_id": "fixture-set",
                    "regression_ids": [],
                    "settings": {"max_attempts": 1, "concurrency": 1},
                }
                check_preview = await client.post(
                    f"{base}/checks/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": check_request},
                )
                assert check_preview.status_code == 200, check_preview.text
                kinds.append(
                    (
                        "/checks",
                        check_request,
                        check_preview.json()["data"]["review_context_hash"],
                    )
                )

                commit = source.commit

                def fail_ready(operation_id, changes, *, intent_hash=None):
                    if any(
                        change.key.collection == "run_events"
                        and change.body is not None
                        and b"segment_ready" in change.body
                        for change in changes
                    ):
                        raise OSError("simulated group member ready commit failure")
                    return commit(operation_id, changes, intent_hash=intent_hash)

                monkeypatch.setattr(source, "commit", fail_ready)
                original_resolve = ProviderBackends.resolve
                original_resolve_captured = ProviderBackends.resolve_captured
                for index, (path, request, review_hash) in enumerate(kinds):
                    operation_id = f"http-incomplete-group-{index}"
                    payload = {
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "expected_review_context_hash": review_hash,
                        "request": request,
                    }
                    first = await client.post(f"{base}{path}", headers=headers, json=payload)
                    assert first.status_code == 500, first.text
                    assert first.json()["error"]["reason"] == "storage_io"
                    failed_source = source.capture_snapshot()
                    groups_before = source.list_ids("execution_groups")
                    active_probe = _CountedProbe(source.execution_active)
                    backend_calls = 0
                    execution_active = source.execution_active

                    def reject_backend_resolve(*args: object, **kwargs: object) -> None:
                        del args, kwargs
                        nonlocal backend_calls
                        backend_calls += 1
                        raise AssertionError("receipt replay resolved the current backend")

                    monkeypatch.setattr(ProviderBackends, "resolve", reject_backend_resolve)
                    monkeypatch.setattr(
                        ProviderBackends, "resolve_captured", reject_backend_resolve
                    )

                    monkeypatch.setattr(source, "execution_active", active_probe)
                    replay = await client.post(f"{base}{path}", headers=headers, json=payload)

                    assert replay.status_code == 409, replay.text
                    assert replay.json()["error"]["reason"] == ("group_acknowledgement_incomplete")
                    group_id = replay.json()["error"]["resource_id"]
                    assert group_id in groups_before
                    assert source.capture_snapshot() == failed_source
                    assert active_probe.calls == 0
                    assert backend_calls == 0
                    monkeypatch.setattr(source, "execution_active", execution_active)
                    monkeypatch.setattr(ProviderBackends, "resolve", original_resolve)
                    monkeypatch.setattr(
                        ProviderBackends, "resolve_captured", original_resolve_captured
                    )

    asyncio.run(exercise())


def test_http_group_start_acknowledges_before_held_execution_preparation_and_replays_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    context = _app(tmp_path)
    execution_started = threading.Event()
    release_execution = threading.Event()
    accepted_tasks: list[asyncio.Task[Any]] = []
    execution_calls = 0

    original_start_group = ExecutionSupervisor.start_group

    async def tracked_start_group(self: ExecutionSupervisor, *args: Any, **kwargs: Any) -> Any:
        task = asyncio.create_task(original_start_group(self, *args, **kwargs))
        accepted_tasks.append(task)
        return await task

    original_execute = GroupExecutionService._execute

    async def held_execute(
        self: GroupExecutionService,
        group: ExecutionGroup,
        segment: ExecutionGroupSegment,
        *,
        deadline: float,
    ) -> GroupProgress:
        nonlocal execution_calls
        execution_calls += 1
        # The group worker must not enter synchronous execution preparation until the
        # supervisor has built and returned the durable acceptance receipt.
        assert accepted_tasks and accepted_tasks[-1].done()
        execution_started.set()
        assert release_execution.wait(30), "held execution preparation was not released"
        return await original_execute(self, group, segment, deadline=deadline)

    monkeypatch.setattr(ExecutionSupervisor, "start_group", tracked_start_group)
    monkeypatch.setattr(GroupExecutionService, "_execute", held_execute)

    async def exercise_body() -> None:
        async with context.api.router.lifespan_context(context.api):
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=context.boundary), base_url=context.origin
                ) as client:
                    headers = await _session(client, context.origin)
                    registration_id = await _register_project(
                        client, headers, tmp_path / "held-group", "Held Group"
                    )
                    source: ApiProjectSource = context.api.state.project_registry.require(
                        registration_id
                    ).source
                    _seed_one_case(source, context.dependencies)
                    base = f"/api/v1/projects/{registration_id}"
                    request = {"run": _run_request(), "orders": 1, "seed": "0"}
                    preview = await client.post(
                        f"{base}/diagnostics/choice-order/preview",
                        headers=headers,
                        json={"schema_version": 1, "request": request},
                    )
                    assert preview.status_code == 200, preview.text
                    payload = {
                        "schema_version": 1,
                        "operation_id": "http-held-group-start",
                        "expected_review_context_hash": preview.json()["data"][
                            "review_context_hash"
                        ],
                        "request": request,
                    }

                    first = await asyncio.wait_for(
                        client.post(
                            f"{base}/diagnostics/choice-order", headers=headers, json=payload
                        ),
                        timeout=12,
                    )
                    assert first.status_code == 202, first.text
                    assert await asyncio.to_thread(execution_started.wait, 5), (
                        "held execution preparation did not start"
                    )
                    first_data = first.json()["data"]
                    assert first_data["replayed"] is False
                    assert first_data["member_run_ids"]
                    assert execution_calls == 1

                    replay = await asyncio.wait_for(
                        client.post(
                            f"{base}/diagnostics/choice-order", headers=headers, json=payload
                        ),
                        timeout=12,
                    )
                    assert replay.status_code == 202, replay.text
                    replay_data = replay.json()["data"]
                    assert replay_data["replayed"] is True
                    assert replay_data["group_id"] == first_data["group_id"]
                    assert replay_data["segment_id"] == first_data["segment_id"]
                    assert replay_data["member_run_ids"] == first_data["member_run_ids"]
                    assert execution_calls == 1

                    release_execution.set()
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        remaining = deadline - time.monotonic()
                        progress = await asyncio.wait_for(
                            client.get(
                                f"{base}/diagnostics/{first_data['group_id']}", headers=headers
                            ),
                            timeout=remaining,
                        )
                        if (
                            progress.status_code == 409
                            and progress.json().get("error", {}).get("reason") == "source_busy"
                        ):
                            await asyncio.sleep(0.01)
                            continue
                        assert progress.status_code == 200, progress.text
                        group = progress.json()["data"]["group"]
                        if group["snapshot_id"] is not None and not any(
                            member["execution_active"] for member in group["members"]
                        ):
                            break
                        await asyncio.sleep(0.01)
                    else:
                        raise AssertionError("held fixture group did not settle after release")
                    snapshot_id = progress.json()["data"]["group"]["snapshot_id"]
                    snapshot = await client.get(
                        f"{base}/diagnostics/{first_data['group_id']}/snapshots/{snapshot_id}",
                        headers=headers,
                    )
                    assert snapshot.status_code == 200, snapshot.text
                    summary = snapshot.json()["data"]["summary"]
                    assert summary["evidence_mode"] == "fixture"
                    assert summary["order_analysis"]["orders"][0]["option_order"] == ["yes", "no"]
            finally:
                release_execution.set()

    asyncio.run(exercise_body())
