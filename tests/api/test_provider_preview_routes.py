"""Provider setup remains secret safe; reviewed previews are read-only API calls."""

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import httpx

from deykit.api.app import create_app
from deykit.api.assets import Asset, AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.api.security import LocalBoundary
from deykit.application.provider_operations import ProviderOperations
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.configuration import create_provider_operations
from deykit.runner.backends import ProviderBackends
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


def _dependencies(
    tmp_path: Path,
    *,
    provider_operations_factory: Callable[
        [ApiProjectSource], ProviderOperations
    ] = create_provider_operations,
) -> ApiDependencies:
    clock = SystemClock()
    return ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=lambda path, create: FileProjectSource(path, create=create),
        recent_store=RecentProjectsStore(clock, tmp_path / "recent.json"),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
        provider_operations_factory=provider_operations_factory,
        backends_factory=ProviderBackends,
    )


def _app(
    tmp_path: Path, *, dependencies: ApiDependencies | None = None
) -> tuple[LocalBoundary, str]:
    origin = "http://127.0.0.1:8765"
    html = b"<html><body>test</body></html>"
    app = create_app(
        LocalServerConfig(
            "127.0.0.1:8765",
            origin,
            AssetCatalog(
                {
                    "index.html": Asset(
                        html, "text/html; charset=utf-8", hashlib.sha256(html).hexdigest()
                    )
                }
            ),
        ),
        dependencies or _dependencies(tmp_path),
    )
    return app, origin


async def _session(client: httpx.AsyncClient, origin: str) -> dict[str, str]:
    bootstrap = await client.post(
        "/api/v1/session/bootstrap",
        headers={"x-deykit-bootstrap": "1", "origin": origin},
        json={"schema_version": 1},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    capability = bootstrap.json()["data"]["capability"]
    return {
        "x-deykit-capability": capability,
        "origin": origin,
        "content-type": "application/json",
    }


def test_provider_routes_configure_without_exposing_or_resolving_credentials(
    tmp_path: Path,
) -> None:
    os_store_calls: list[bool] = []
    factory_calls: list[bool] = []

    def forbidden_store() -> NoReturn:
        os_store_calls.append(True)
        raise AssertionError("configuration must not open the OS secret store")

    def provider_operations(source: ApiProjectSource) -> ProviderOperations:
        factory_calls.append(True)
        return create_provider_operations(
            source,
            environment={},
            os_store_factory=forbidden_store,
        )

    app, origin = _app(
        tmp_path,
        dependencies=_dependencies(tmp_path, provider_operations_factory=provider_operations),
    )

    async def exercise() -> None:
        async with app.app.router.lifespan_context(app.app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=origin
            ) as client:
                headers = await _session(client, origin)
                project = await client.post(
                    "/api/v1/projects/register",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "register-provider-project",
                        "action": "create",
                        "path": str(tmp_path / "provider-project"),
                        "name": "Provider project",
                    },
                )
                assert project.status_code == 200, project.text
                registration_id = project.json()["data"]["registration_id"]
                path = f"/api/v1/projects/{registration_id}/providers/provider-1"
                secret_reference = "env:DEYKIT_TEST_SECRET_SENTINEL"
                configured = await client.put(
                    path,
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "configure-provider",
                        "profile_id": "provider-1",
                        "adapter": "jev",
                        "requested_model": "jev-latest",
                        "destination": JEV_DESTINATION,
                        "credential_ref": secret_reference,
                    },
                )
                assert configured.status_code == 200, configured.text
                profile = configured.json()["data"]["profile"]
                assert profile["credential_configured"] is True
                assert profile["credential_kind"] == "env"
                assert "credential_ref" not in profile
                assert secret_reference not in configured.text

                status = await client.get(
                    f"{path}/credential-status",
                    headers={"x-deykit-capability": headers["x-deykit-capability"]},
                )
                assert status.status_code == 200, status.text
                assert status.json()["data"] == {
                    "schema_version": 1,
                    "profile_id": "provider-1",
                    "configured": True,
                    "available": False,
                    "kind": "env",
                }
                assert secret_reference not in status.text

    asyncio.run(exercise())
    assert factory_calls
    assert os_store_calls == []


def test_run_and_choice_order_previews_are_protected_and_do_not_create_runs(
    tmp_path: Path,
) -> None:
    app, origin = _app(tmp_path)

    async def exercise() -> None:
        async with app.app.router.lifespan_context(app.app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=origin
            ) as client:
                headers = await _session(client, origin)
                demo = await client.post(
                    "/api/v1/projects/demo",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "create-preview-demo",
                        "path": str(tmp_path / "preview-demo"),
                    },
                )
                assert demo.status_code == 200, demo.text
                data = demo.json()["data"]["demo"]
                registration_id = demo.json()["data"]["registration"]["registration_id"]
                request = {
                    "decision_id": data["decision_id"],
                    "dataset_id": data["dataset_id"],
                    "mode": "fixture",
                    "fixture_set_id": data["fixture_set_id"],
                }
                run = await client.post(
                    f"/api/v1/projects/{registration_id}/runs/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": request},
                )
                assert run.status_code == 200, run.text
                assert run.json()["data"]["dry_run"] is True
                assert len(run.json()["data"]["review_context_hash"]) == 64

                group = await client.post(
                    f"/api/v1/projects/{registration_id}/diagnostics/choice-order/preview",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "request": {"run": request, "orders": 2, "seed": 7},
                    },
                )
                assert group.status_code == 200, group.text
                assert group.json()["data"]["dry_run"] is True
                assert len(group.json()["data"]["members"]) == 2
                registration = app.app.state.project_registry.require(registration_id)
                assert registration.source.list_ids("runs") == ()
                assert registration.source.list_ids("execution_groups") == ()

    asyncio.run(exercise())
