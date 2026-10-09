"""The app drains admitted source work before releasing retained handles."""

import asyncio
import hashlib
from threading import Event

import httpx

from deykit.api.app import create_app
from deykit.api.assets import Asset, AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource
from deykit.providers.configuration import create_provider_operations
from deykit.runner.backends import ProviderBackends


def test_shutdown_waits_for_admitted_request_before_closing_retained_source(tmp_path):
    origin = "http://127.0.0.1:8765"
    clock = SystemClock()
    opened: list[FileProjectSource] = []

    def source_factory(path, create):
        source = FileProjectSource(path, create=create)
        opened.append(source)
        return source

    shell = b"<html><body>shell</body></html>"
    app = create_app(
        LocalServerConfig(
            "127.0.0.1:8765",
            origin,
            AssetCatalog(
                {
                    "index.html": Asset(
                        shell,
                        "text/html; charset=utf-8",
                        hashlib.sha256(shell).hexdigest(),
                    )
                }
            ),
        ),
        ApiDependencies(
            clock=clock,
            id_factory=new_id,
            source_factory=source_factory,
            recent_store=RecentProjectsStore(clock, tmp_path / "recent.json"),
            demo_staging_factory=DemoStagingSource,
            demo_destination_factory=FileDemoDestinationFactory(),
            provider_operations_factory=create_provider_operations,
            backends_factory=ProviderBackends,
        ),
    )

    async def exercise() -> None:
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin)
        lifespan = app.app.router.lifespan_context(app.app)
        await lifespan.__aenter__()
        request_task: asyncio.Task[httpx.Response] | None = None
        shutdown_task: asyncio.Task[bool] | None = None
        started = Event()
        release = Event()
        try:
            bootstrap = await client.post(
                "/api/v1/session/bootstrap",
                headers={"origin": origin, "x-deykit-bootstrap": "1"},
                json={"schema_version": 1},
            )
            capability = bootstrap.json()["data"]["capability"]
            headers = {
                "origin": origin,
                "x-deykit-capability": capability,
                "content-type": "application/json",
            }
            registered = await client.post(
                "/api/v1/projects/register",
                headers=headers,
                json={
                    "schema_version": 1,
                    "operation_id": "shutdown-project",
                    "action": "create",
                    "path": str(tmp_path / "retained"),
                    "name": "Retained",
                },
            )
            assert registered.status_code == 200
            source = opened[0]

            def blocked_rebuild() -> int:
                started.set()
                if not release.wait(timeout=5):
                    raise AssertionError("test did not release the admitted worker")
                return 1

            source.rebuild_index = blocked_rebuild
            registration_id = registered.json()["data"]["registration_id"]
            request_task = asyncio.create_task(
                client.post(
                    f"/api/v1/projects/{registration_id}/rebuild-index",
                    headers=headers,
                    json={"schema_version": 1},
                )
            )
            assert await asyncio.to_thread(started.wait, 5)

            shutdown_task = asyncio.create_task(lifespan.__aexit__(None, None, None))
            await asyncio.sleep(0)
            assert not shutdown_task.done()
            assert not source.files.closed

            release.set()
            response = await request_task
            assert response.status_code == 200
            assert await shutdown_task is False
            assert source.files.closed
            revoked_response = await client.get(
                f"/api/v1/projects/{registration_id}",
                headers={"x-deykit-capability": capability},
            )
            assert revoked_response.status_code == 403
            assert revoked_response.json()["error"]["code"] == "local_access_denied"
        finally:
            release.set()
            if request_task is not None and not request_task.done():
                await request_task
            if shutdown_task is not None and not shutdown_task.done():
                await shutdown_task
            await client.aclose()

    asyncio.run(exercise())
