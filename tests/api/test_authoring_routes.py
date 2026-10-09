"""The protected API preserves editor source through its exact-source operations."""

import asyncio
import hashlib

import httpx
import pytest
from pydantic import ValidationError

from deykit.api.app import create_app
from deykit.api.assets import Asset, AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.authoring import EditorTransformRequest, MappingTransformRequest
from deykit.api.recent import RecentProjectsStore
from deykit.api.routes.authoring import _revision
from deykit.api.runtime import SystemClock, new_id
from deykit.application.authoring_views import (
    ReorderOptions,
    ReplaceMappingFields,
    ReplaceOptionAliases,
    SetSelectedFields,
)
from deykit.application.definitions import Versioned, revision_editor_source
from deykit.contracts.json_value import dump_json
from deykit.contracts.records import ChoiceDefinition, ChoiceOption, ChoiceQuestion, DecisionRevision
from deykit.providers.configuration import create_provider_operations
from deykit.runner.backends import ProviderBackends
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


def test_saved_revision_projection_includes_canonical_editor_source():
    definition = ChoiceDefinition(
        input_kind="json",
        input_schema_source='{"type":"number","minimum":900719925474099312345.6789}',
        selected_fields=("amount",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose.",
                options=(
                    ChoiceOption(id="a", name="A", description=None),
                    ChoiceOption(id="b", name="B", description=""),
                ),
            ),
        ),
    )
    revision = DecisionRevision(
        id="revision",
        decision_id="decision",
        definition=definition,
        content_hash="a" * 64,
        created_at="2026-10-09T12:00:00Z",
    )

    projected = _revision(Versioned(revision, "b" * 64))

    assert projected.editor_source == revision_editor_source(revision)
    assert "900719925474099312345.6789" in projected.editor_source
    assert projected.model_dump(mode="json")["editor_source"] == projected.editor_source


def test_authoring_edit_dtos_normalize_only_declared_json_array_fields():
    editor_base = {
        "schema_version": 1,
        "editor_source": "{}",
        "expected_draft_etag": "a" * 64,
    }
    reordered = EditorTransformRequest.model_validate(
        {
            **editor_base,
            "edit": {"kind": "reorder_options", "option_ids": ["yes", "no"]},
        }
    )
    assert isinstance(reordered.edit, ReorderOptions)
    assert reordered.edit.option_ids == ("yes", "no")
    selected = EditorTransformRequest.model_validate(
        {
            **editor_base,
            "edit": {"kind": "set_selected_fields", "selected_fields": ["name"]},
        }
    )
    assert isinstance(selected.edit, SetSelectedFields)
    assert selected.edit.selected_fields == ("name",)
    with pytest.raises(ValidationError):
        EditorTransformRequest.model_validate(
            {**editor_base, "edit": {"kind": "reorder_options", "option_ids": "yes"}}
        )
    with pytest.raises(ValidationError):
        EditorTransformRequest.model_validate(
            {**editor_base, "edit": {"kind": "set_selected_fields", "selected_fields": [1]}}
        )

    mapping_base = {"schema_version": 1, "mapping_source": "{}"}
    mapping_fields = MappingTransformRequest.model_validate(
        {
            **mapping_base,
            "edit": {
                "kind": "replace_fields",
                "fields": [{"source": "input", "target": "input", "parse_json": False}],
            },
        }
    )
    assert isinstance(mapping_fields.edit, ReplaceMappingFields)
    assert len(mapping_fields.edit.fields) == 1
    assert mapping_fields.edit.fields[0].source == "input"
    aliases = MappingTransformRequest.model_validate(
        {
            **mapping_base,
            "edit": {
                "kind": "replace_option_aliases",
                "option_aliases": [{"value": "yes", "option_id": "yes"}],
            },
        }
    )
    assert isinstance(aliases.edit, ReplaceOptionAliases)
    assert aliases.edit.option_aliases[0].option_id == "yes"
    with pytest.raises(ValidationError):
        MappingTransformRequest.model_validate(
            {**mapping_base, "edit": {"kind": "replace_fields", "fields": "input"}}
        )


def test_decision_editor_projection_and_transform_are_protected_and_exact(tmp_path):
    origin = "http://127.0.0.1:8765"
    clock = SystemClock()
    dependencies = ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=lambda path, create: FileProjectSource(path, create=create),
        recent_store=RecentProjectsStore(clock, tmp_path / "recent.json"),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
        provider_operations_factory=create_provider_operations,
        backends_factory=ProviderBackends,
    )
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
        dependencies,
    )
    editor_source = dump_json(
        {
            "schema_version": 1,
            "input_kind": "text",
            "input_schema_source": None,
            "selected_fields": [],
            "questions": [
                {
                    "id": "question",
                    "kind": "choice",
                    "instructions": "Choose.",
                    "options": [
                        {"id": "yes", "name": "Yes", "description": None},
                        {"id": "no", "name": "No", "description": ""},
                    ],
                }
            ],
        }
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
                capability = bootstrap.json()["data"]["capability"]
                headers = {
                    "x-deykit-capability": capability,
                    "origin": origin,
                    "content-type": "application/json",
                }
                registered = await client.post(
                    "/api/v1/projects/register",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "register-authoring",
                        "action": "create",
                        "path": str(tmp_path / "authoring-project"),
                        "name": "Authoring",
                    },
                )
                assert registered.status_code == 200, registered.text
                registration_id = registered.json()["data"]["registration_id"]
                created = await client.post(
                    f"/api/v1/projects/{registration_id}/decisions",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "create-decision",
                        "decision_id": "decision",
                        "name": "Decision",
                        "editor_source": editor_source,
                    },
                )
                assert created.status_code == 200, created.text
                etag = created.json()["data"]["draft"]["etag"]
                projected = await client.post(
                    f"/api/v1/projects/{registration_id}/decisions/decision/editor-projection",
                    headers=headers,
                    json={"schema_version": 1, "editor_source": editor_source},
                )
                assert projected.status_code == 200, projected.text
                projection = projected.json()["data"]
                assert projection["editor_source"] == editor_source
                assert (
                    projection["source_hash"]
                    == hashlib.sha256(editor_source.encode("utf-8")).hexdigest()
                )
                assert projection["form"]["options"][1]["description"] == ""
                transformed = await client.post(
                    f"/api/v1/projects/{registration_id}/decisions/decision/editor-transform",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "editor_source": editor_source,
                        "expected_draft_etag": etag,
                        "edit": {
                            "kind": "set_instructions",
                            "value": "Choose carefully.",
                        },
                    },
                )
                assert transformed.status_code == 200, transformed.text
                data = transformed.json()["data"]
                assert (
                    data["transform"]["projection"]["form"]["instructions"] == "Choose carefully."
                )
                assert data["incompatible_references"] == []

                decision_path = f"/api/v1/projects/{registration_id}/decisions/decision"
                current = await client.get(decision_path, headers=headers)
                assert current.status_code == 200, current.text
                draft = current.json()["data"]["draft"]
                remove_last_option = await client.post(
                    f"{decision_path}/editor-transform",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "editor_source": draft["record"]["editor_source"],
                        "expected_draft_etag": draft["etag"],
                        "edit": {"kind": "remove_option", "id": "no"},
                    },
                )
                assert remove_last_option.status_code == 200, remove_last_option.text
                reviewed = remove_last_option.json()["data"]
                assert reviewed["transform"]["projection"]["validation_advice"]
                assert len(reviewed["transform"]["projection"]["form"]["options"]) == 1
                assert reviewed["incompatible_references"] is None

                unchanged = await client.get(decision_path, headers=headers)
                assert unchanged.status_code == 200, unchanged.text
                after_draft = unchanged.json()["data"]["draft"]
                assert after_draft["record"]["editor_source"] == draft["record"]["editor_source"]
                assert after_draft["etag"] == draft["etag"]

    asyncio.run(exercise())
