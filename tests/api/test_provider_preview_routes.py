"""Provider setup remains secret safe; reviewed previews are read-only API calls."""

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import httpx
import pytest
from pydantic import ValidationError

from deykit.api.app import create_app
from deykit.api.assets import Asset, AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.dto.execution import (
    CheckRequestDTO,
    ChoiceOrderPreviewRequest,
    RunRequestDTO,
)
from deykit.api.dto.providers import FixtureCreateRequest
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.api.security import LocalBoundary
from deykit.application.provider_operations import ProviderOperations
from deykit.contracts.provider_configuration import ModelDescription
from deykit.contracts.records import ProviderProfile
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


def test_provider_model_listing_requires_version_body_without_opening_secrets(
    tmp_path: Path,
) -> None:
    model_calls: list[tuple[str, float]] = []
    os_store_calls: list[bool] = []

    class OfflineModels:
        async def models(
            self, profile: ProviderProfile, *, timeout_seconds: float
        ) -> tuple[ModelDescription, ...]:
            model_calls.append((profile.id, timeout_seconds))
            return (ModelDescription("model-1", "Local fake", "2026-01-01"),)

    def forbidden_store() -> NoReturn:
        os_store_calls.append(True)
        raise AssertionError("model listing must not open the OS secret store")

    def provider_operations(source: ApiProjectSource) -> ProviderOperations:
        return create_provider_operations(
            source,
            environment={},
            os_store_factory=forbidden_store,
            model_lister=OfflineModels(),
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
                        "operation_id": "register-model-project",
                        "action": "create",
                        "path": str(tmp_path / "model-project"),
                        "name": "Model project",
                    },
                )
                assert project.status_code == 200, project.text
                registration_id = project.json()["data"]["registration_id"]
                profile_path = f"/api/v1/projects/{registration_id}/providers/provider-1"
                configured = await client.put(
                    profile_path,
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "configure-model-profile",
                        "profile_id": "provider-1",
                        "adapter": "jev",
                        "requested_model": "jev-latest",
                        "destination": JEV_DESTINATION,
                    },
                )
                assert configured.status_code == 200, configured.text

                model_path = f"{profile_path}/models?timeout_seconds=12"
                missing_body = await client.post(model_path, headers=headers)
                assert missing_body.status_code == 422, missing_body.text
                assert model_calls == []

                response = await client.post(
                    model_path,
                    headers=headers,
                    json={"schema_version": 1},
                )
                assert response.status_code == 200, response.text
                assert response.json()["data"] == {
                    "schema_version": 1,
                    "profile_id": "provider-1",
                    "network_check": True,
                    "inference_calls": 0,
                    "models": [
                        {
                            "schema_version": 1,
                            "name": "model-1",
                            "description": "Local fake",
                            "release_date": "2026-01-01",
                        }
                    ],
                }
                assert model_calls == [("provider-1", 12.0)]

    asyncio.run(exercise())
    assert os_store_calls == []


def test_choice_order_seed_requires_signed_64_bit_decimal_text() -> None:
    request_base = {
        "schema_version": 1,
        "request": {
            "run": {
                "decision_id": "decision-1",
                "dataset_id": "dataset-1",
                "mode": "fixture",
                "fixture_set_id": "fixture-1",
            },
            "orders": 2,
        },
    }
    for seed in ("-9223372036854775808", "9007199254740993", "9223372036854775807"):
        request = ChoiceOrderPreviewRequest.model_validate(
            {**request_base, "request": {**request_base["request"], "seed": seed}}
        )
        assert request.request.seed == seed

    for seed in (
        1,
        "+1",
        "01",
        "-0",
        "9223372036854775808",
        "-9223372036854775809",
    ):
        with pytest.raises(ValidationError):
            ChoiceOrderPreviewRequest.model_validate(
                {**request_base, "request": {**request_base["request"], "seed": seed}}
            )


def test_fixture_create_dto_accepts_only_json_binding_source_arrays() -> None:
    request_base = {
        "schema_version": 1,
        "operation_id": "fixture-create",
        "fixture_set_id": "fixture-1",
        "decision_id": "decision-1",
        "dataset_id": "dataset-1",
        "name": "Authored fixture",
        "model_identity": "jev/model",
    }
    binding_sources = ('{"large":9007199254740993}', '"unchanged text"')
    request = FixtureCreateRequest.model_validate(
        {**request_base, "binding_sources": list(binding_sources)}
    )
    assert request.binding_sources == binding_sources

    for invalid in ("source", [], ["source", 1]):
        with pytest.raises(ValidationError):
            FixtureCreateRequest.model_validate({**request_base, "binding_sources": invalid})


def test_execution_preview_dtos_accept_json_arrays_and_keep_application_constraints() -> None:
    run_data = {
        "decision_id": "decision-1",
        "dataset_id": "dataset-1",
        "mode": "fixture",
        "fixture_set_id": "fixture-1",
        "case_ids": ["case-1"],
        "option_order": ["yes", "no"],
        "regression_ids": [],
    }
    run = RunRequestDTO.model_validate(run_data).to_application()
    assert run.case_ids == ("case-1",)
    assert run.option_order == ("yes", "no")
    assert run.regression_ids == ()

    regression_data = {
        "decision_id": "decision-1",
        "dataset_id": "dataset-1",
        "mode": "fixture",
        "fixture_set_id": "fixture-1",
        "regression_ids": ["regression-1"],
    }
    regression_request = RunRequestDTO.model_validate(regression_data).to_application()
    assert regression_request.case_ids == ()
    assert regression_request.regression_ids == ("regression-1",)

    check_data = {
        "decision_id": "decision-1",
        "mode": "fixture",
        "fixture_set_id": "fixture-1",
        "regression_ids": ["regression-1"],
    }
    assert CheckRequestDTO.model_validate(check_data).to_application().regression_ids == (
        "regression-1",
    )

    for invalid in (
        {**run_data, "case_ids": "case-1"},
        {**run_data, "option_order": ["yes", 4]},
        {**run_data, "case_ids": ["case-1", "case-1"]},
        {**run_data, "regression_ids": ["regression-1"]},
    ):
        with pytest.raises(ValidationError):
            RunRequestDTO.model_validate(invalid)
    with pytest.raises(ValidationError):
        CheckRequestDTO.model_validate({**check_data, "regression_ids": ["regression-1"] * 2})


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
                        "request": {
                            "run": request,
                            "orders": 2,
                            "seed": "9007199254740993",
                        },
                    },
                )
                assert group.status_code == 200, group.text
                assert group.json()["data"]["dry_run"] is True
                assert len(group.json()["data"]["members"]) == 2
                assert group.json()["data"]["seed"] == "9007199254740993"
                registration = app.app.state.project_registry.require(registration_id)
                assert registration.source.list_ids("runs") == ()
                assert registration.source.list_ids("execution_groups") == ()

    asyncio.run(exercise())
