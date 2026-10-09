"""Actual ASGI regression for a frozen standalone run without durable readiness."""

import asyncio
import time
from pathlib import Path

import httpx

from deykit.api.dependencies import ApiProjectSource
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.runner.backends import ProviderBackends
from test_m09_http_guards import (
    _app,
    _register_project,
    _run_request,
    _seed_one_case,
    _session,
)


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
                    "expected_review_context_hash": preview.json()["data"][
                        "review_context_hash"
                    ],
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
                active_calls = 0
                backend_calls = 0
                execution_active = source.execution_active
                original_resolve = ProviderBackends.resolve
                original_resolve_captured = ProviderBackends.resolve_captured

                def count_active() -> bool:
                    nonlocal active_calls
                    active_calls += 1
                    return execution_active()

                def reject_backend_resolve(*args: object, **kwargs: object) -> None:
                    del args, kwargs
                    nonlocal backend_calls
                    backend_calls += 1
                    raise AssertionError("receipt replay resolved the current backend")

                monkeypatch.setattr(source, "execution_active", count_active)
                monkeypatch.setattr(ProviderBackends, "resolve", reject_backend_resolve)
                monkeypatch.setattr(
                    ProviderBackends, "resolve_captured", reject_backend_resolve
                )
                replay = await client.post(f"{base}/runs", headers=headers, json=start)

                assert replay.status_code == 409, replay.text
                assert first.json()["error"]["reason"] == "start_acknowledgement_incomplete"
                assert replay.json()["error"]["reason"] == "start_acknowledgement_incomplete"
                assert first.json()["error"]["resource_id"] == replay.json()["error"][
                    "resource_id"
                ]
                assert source.capture_snapshot() == before_replay
                assert active_calls == 0 and backend_calls == 0
                monkeypatch.setattr(source, "execution_active", execution_active)
                monkeypatch.setattr(ProviderBackends, "resolve", original_resolve)
                monkeypatch.setattr(
                    ProviderBackends, "resolve_captured", original_resolve_captured
                )

    asyncio.run(exercise())


def test_http_group_incomplete_receipt_replay_is_409_for_both_group_kinds(
    tmp_path: Path, monkeypatch
) -> None:
    context = _app(tmp_path)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=context.boundary, raise_app_exceptions=False
                ),
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
                    assert progress.status_code == 200, progress.text
                    if progress.json()["data"]["latest_result_snapshot_id"]:
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("fixture baseline did not settle")
                RegressionService(source, context.dependencies.clock, context.dependencies.id_factory).add(
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
                    assert first.json()["error"]["reason"] == "execution_failed"
                    failed_source = source.capture_snapshot()
                    groups_before = source.list_ids("execution_groups")
                    active_calls = 0
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

                    def count_active() -> bool:
                        nonlocal active_calls
                        active_calls += 1
                        return execution_active()

                    monkeypatch.setattr(source, "execution_active", count_active)
                    replay = await client.post(f"{base}{path}", headers=headers, json=payload)

                    assert replay.status_code == 409, replay.text
                    assert replay.json()["error"]["reason"] == (
                        "group_acknowledgement_incomplete"
                    )
                    group_id = replay.json()["error"]["resource_id"]
                    assert group_id in groups_before
                    assert source.capture_snapshot() == failed_source
                    assert active_calls == 0
                    assert backend_calls == 0
                    monkeypatch.setattr(source, "execution_active", execution_active)
                    monkeypatch.setattr(ProviderBackends, "resolve", original_resolve)
                    monkeypatch.setattr(
                        ProviderBackends, "resolve_captured", original_resolve_captured
                    )

    asyncio.run(exercise())
