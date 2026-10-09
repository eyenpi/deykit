"""Real API project flows share application services and durable project receipts."""

import asyncio
import hashlib

import httpx

from deykit.api.app import create_app
from deykit.api.assets import Asset, AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource


def test_register_overview_demo_replay_and_recent_projects(tmp_path):
    html = b"<html><body>local shell</body></html>"
    port = 8765
    origin = f"http://127.0.0.1:{port}"
    clock = SystemClock()
    dependencies = ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=lambda path, create: FileProjectSource(path, create=create),
        recent_store=RecentProjectsStore(clock, tmp_path / "recent.json"),
        demo_staging_factory=DemoStagingSource,
    )
    app = create_app(
        LocalServerConfig(
            f"127.0.0.1:{port}",
            origin,
            AssetCatalog(
                {
                    "index.html": Asset(
                        html, "text/html; charset=utf-8", hashlib.sha256(html).hexdigest()
                    )
                }
            ),
        ),
        dependencies,
    )

    async def exercise() -> None:
        async with app.app.router.lifespan_context(app.app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=origin
            ) as client:
                bootstrap = await client.post(
                    "/api/v1/session/bootstrap",
                    headers={"x-deykit-bootstrap": "1", "origin": origin},
                    json={"schema_version": 1},
                )
                assert bootstrap.status_code == 200
                capability = bootstrap.json()["data"]["capability"]
                headers = {
                    "x-deykit-capability": capability,
                    "origin": origin,
                    "content-type": "application/json",
                }

                project_path = str(tmp_path / "Project ü")
                created = await client.post(
                    "/api/v1/projects/register",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "create-project",
                        "action": "create",
                        "path": project_path,
                        "name": "Project",
                    },
                )
                assert created.status_code == 200, created.text
                registration = created.json()["data"]
                registration_id = registration["registration_id"]
                assert registration["project"]["name"] == "Project"
                assert created.headers["etag"] == f'"{registration["project_etag"]}"'

                overview = await client.get(
                    f"/api/v1/projects/{registration_id}/overview",
                    headers={"x-deykit-capability": capability},
                )
                assert overview.status_code == 200, overview.text
                assert overview.headers["etag"] == f'"{registration["project_etag"]}"'
                assert overview.json()["data"]["decisions"] == []
                assert overview.json()["data"]["datasets"] == []

                validated = await client.post(
                    f"/api/v1/projects/{registration_id}/validate",
                    headers=headers,
                    json={"schema_version": 1},
                )
                assert validated.status_code == 200, validated.text
                rebuilt = await client.post(
                    f"/api/v1/projects/{registration_id}/rebuild-index",
                    headers=headers,
                    json={"schema_version": 1},
                )
                assert rebuilt.status_code == 200, rebuilt.text
                assert rebuilt.json()["data"]["record_count"].isdigit()

                project_root = tmp_path / "Project ü"
                moved_root = tmp_path / "Project moved"
                replacement_sentinel = project_root / "replacement.txt"
                project_root.rename(moved_root)
                project_root.mkdir()
                replacement_sentinel.write_text("preserve replacement")
                anchored_rebuild = await client.post(
                    f"/api/v1/projects/{registration_id}/rebuild-index",
                    headers=headers,
                    json={"schema_version": 1},
                )
                assert anchored_rebuild.status_code == 200, anchored_rebuild.text
                assert replacement_sentinel.read_text() == "preserve replacement"

                demo_path = str(tmp_path / "Sandbox demo")
                payload = {
                    "schema_version": 1,
                    "operation_id": "create-demo",
                    "path": demo_path,
                }
                demo = await client.post(
                    "/api/v1/projects/demo", headers=headers, json=payload
                )
                assert demo.status_code == 200, demo.text
                data = demo.json()["data"]
                assert data["demo"]["evidence_mode"] == "authored_fixture"
                assert (
                    data["demo"]["case_count"],
                    data["demo"]["binding_count"],
                    data["demo"]["label_count"],
                ) == ("12", "11", "9")

                replay = await client.post(
                    "/api/v1/projects/demo", headers=headers, json=payload
                )
                assert replay.status_code == 200, replay.text
                assert replay.json()["data"]["demo"]["replayed"] is True
                assert replay.json()["data"]["registration"]["registration_id"] == data[
                    "registration"
                ]["registration_id"]

                recent = await client.get(
                    "/api/v1/projects/recent",
                    headers={"x-deykit-capability": capability},
                )
                assert recent.status_code == 200
                assert [item["path"] for item in recent.json()["data"]["items"]] == [
                    demo_path,
                    project_path,
                ]

    asyncio.run(exercise())
