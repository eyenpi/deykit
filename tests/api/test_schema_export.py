import json
from pathlib import Path

import pytest

from deykit.api.schema import contract_documents, export_contracts


def test_schema_export_has_only_real_routes_and_required_version(tmp_path: Path) -> None:
    first = contract_documents()
    assert first == contract_documents()
    openapi = json.loads(first["openapi.json"])
    paths = set(openapi["paths"])
    assert "/api/v1/session/bootstrap" in paths
    assert "/api/v1/projects/register" in paths
    assert "/api/v1/projects/{registration_id}/overview" in paths
    providers = openapi["paths"]["/api/v1/projects/{registration_id}/providers"]
    assert set(providers) == {"get"}
    assert providers["get"]["operationId"] == "listProviderProfiles"
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
