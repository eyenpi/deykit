import hashlib
import json
from pathlib import Path

import pytest

from deykit.api.assets import AssetCatalog
from deykit.api.schema import contract_documents, export_contracts
from deykit.application.errors import ServiceFailure


def test_schema_export_has_only_real_routes_and_required_version(tmp_path: Path) -> None:
    first = contract_documents()
    assert first == contract_documents()
    openapi = json.loads(first["openapi.json"])
    paths = set(openapi["paths"])
    assert "/api/v1/session/bootstrap" in paths
    assert "/api/v1/projects/register" in paths
    assert "/api/v1/projects/{registration_id}/overview" in paths
    assert "/api/v1/projects/{registration_id}/providers" not in paths
    request = openapi["components"]["schemas"]["BootstrapRequest"]
    assert request["required"] == ["schema_version"]
    assert request["additionalProperties"] is False
    assert "HTTPValidationError" not in openapi["components"]["schemas"]
    schemas = json.loads(first["schemas.json"])
    assert "schema_version" in schemas["Success_BootstrapReply_"]["required"]
    failure = schemas["Failure"]
    assert failure["properties"]["selection"]["anyOf"]
    assert failure["properties"]["selection"]["default"] is None
    export_contracts(tmp_path)
    export_contracts(tmp_path, check=True)
    (tmp_path / "openapi.json").write_text("{}")
    with pytest.raises(SystemExit, match="stale local API contract"):
        export_contracts(tmp_path, check=True)


def test_assets_fail_closed_and_only_load_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "static"
    root.mkdir()
    monkeypatch.setattr("deykit.api.assets.files", lambda _: tmp_path)
    with pytest.raises(ServiceFailure) as caught:
        AssetCatalog.from_package()
    assert caught.value.error.reason == "ui_assets_unavailable"
    content = b"<html>test-only</html>"
    (root / "index.html").write_bytes(content)
    (root / "unlisted.txt").write_text("must never be exposed")
    entry = {
        "name": "index.html",
        "content_type": "text/html; charset=utf-8",
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    (root / "manifest.json").write_text(json.dumps({"schema_version": 1, "assets": [entry]}))
    catalog = AssetCatalog.from_package()
    assert set(catalog.assets) == {"index.html"}
    assert catalog.assets["index.html"].body == content
    (root / "index.html").write_bytes(content + b"tamper")
    with pytest.raises(ServiceFailure):
        AssetCatalog.from_package()
    entry["name"] = "../outside.html"
    (root / "manifest.json").write_text(json.dumps({"schema_version": 1, "assets": [entry]}))
    with pytest.raises(ServiceFailure):
        AssetCatalog.from_package()
