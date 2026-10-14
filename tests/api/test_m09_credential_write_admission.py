"""Credential write outcomes stay honest at the installed HTTP boundary."""

import asyncio
from pathlib import Path

import httpx

from deykit.api.app import create_app
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.configuration import create_provider_operations
from deykit.providers.profiles import ProviderProfiles
from deykit.runner.backends import ProviderBackends
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


class MutateThenFailStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.calls: list[str] = []

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.calls.append("set")
        self.values[(service, username)] = password
        raise RuntimeError("SECRET_SENTINEL from fake keyring")

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append("forget")
        self.values.pop((service, username), None)
        raise RuntimeError("SECRET_SENTINEL from fake keyring")


def test_os_set_and_forget_mutate_then_fail_return_safe_http500(tmp_path: Path) -> None:
    store = MutateThenFailStore()
    clock = SystemClock()
    origin = "http://127.0.0.1:8748"

    def provider_operations(source):
        return create_provider_operations(source, environment={}, os_store_factory=lambda: store)

    dependencies = ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=lambda path, create: FileProjectSource(path, create=create),
        recent_store=RecentProjectsStore(clock, tmp_path / "recent.json"),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
        provider_operations_factory=provider_operations,
        backends_factory=ProviderBackends,
    )
    app = create_app(LocalServerConfig("127.0.0.1:8748", origin), dependencies)

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
                assert bootstrap.status_code == 200, bootstrap.text
                headers = {
                    "x-deykit-capability": bootstrap.json()["data"]["capability"],
                    "origin": origin,
                }
                registered = await client.post(
                    "/api/v1/projects/register",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "register-credential-project",
                        "action": "create",
                        "path": str(tmp_path / "credential-project"),
                        "name": "Credential project",
                    },
                )
                assert registered.status_code == 200, registered.text
                registration_id = registered.json()["data"]["registration_id"]
                source = app.app.state.project_registry.require(registration_id).source
                profiles = ProviderProfiles(source)
                profile_path = f"/api/v1/projects/{registration_id}/providers/profile"
                configured = await client.put(
                    profile_path,
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "configure-credential-profile",
                        "profile_id": "profile",
                        "adapter": "jev",
                        "requested_model": "jev-1.13.0",
                        "destination": JEV_DESTINATION,
                    },
                )
                assert configured.status_code == 200, configured.text
                etag = configured.json()["data"]["profile"]["etag"]
                admitted_source = source.capture_snapshot()
                operation_id = "set-credential-unknown"
                set_response = await client.post(
                    f"{profile_path}/credential-os-store",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "expected_etag": etag,
                        "credential_value": "SECRET_SENTINEL",
                    },
                )
                assert set_response.status_code == 500, set_response.text
                assert set_response.json()["error"]["code"] == "internal_error"
                assert set_response.json()["error"]["reason"] == "credential_update_outcome_unknown"
                assert set_response.json()["error"]["resource_id"] == "profile"
                assert "SECRET_SENTINEL" not in set_response.text
                assert store.values[("deykit", "profile")] == "SECRET_SENTINEL"
                after_set = await client.get(profile_path, headers=headers)
                assert after_set.status_code == 200, after_set.text
                assert after_set.json()["data"]["etag"] == etag
                assert after_set.json()["data"]["credential_configured"] is False
                assert after_set.json()["data"]["credential_kind"] is None
                assert source.capture_snapshot() == admitted_source
                assert (
                    profiles.credential_replay(
                        "profile",
                        "keyring:deykit/profile",
                        expected_etag=etag,
                        operation_id=operation_id,
                    )
                    is None
                )

                attached = await client.put(
                    profile_path,
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "attach-existing-keyring-reference",
                        "profile_id": "profile",
                        "adapter": "jev",
                        "requested_model": "jev-1.13.0",
                        "destination": JEV_DESTINATION,
                        "credential_ref": "keyring:deykit/profile",
                        "expected_etag": etag,
                    },
                )
                assert attached.status_code == 200, attached.text
                etag = attached.json()["data"]["profile"]["etag"]
                admitted_source = source.capture_snapshot()
                forget_response = await client.post(
                    f"{profile_path}/credential-forget",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "forget-credential-unknown",
                        "expected_etag": etag,
                    },
                )
                assert forget_response.status_code == 500, forget_response.text
                assert forget_response.json()["error"]["code"] == "internal_error"
                assert (
                    forget_response.json()["error"]["reason"] == "credential_update_outcome_unknown"
                )
                assert forget_response.json()["error"]["resource_id"] == "profile"
                assert "SECRET_SENTINEL" not in forget_response.text
                assert store.values == {}
                assert store.calls == ["set", "forget"]
                after_forget = await client.get(profile_path, headers=headers)
                assert after_forget.status_code == 200, after_forget.text
                assert after_forget.json()["data"]["etag"] == etag
                assert after_forget.json()["data"]["credential_configured"] is True
                assert after_forget.json()["data"]["credential_kind"] == "keyring"
                assert source.capture_snapshot() == admitted_source
                assert (
                    profiles.credential_replay(
                        "profile",
                        None,
                        expected_etag=etag,
                        operation_id="forget-credential-unknown",
                    )
                    is None
                )

    asyncio.run(exercise())
    project_path = tmp_path / "credential-project"
    assert not any(
        b"SECRET_SENTINEL" in path.read_bytes()
        for path in project_path.rglob("*")
        if path.is_file()
    )
