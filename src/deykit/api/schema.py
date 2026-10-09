"""Deterministic local schema export. Only implemented routes appear in OpenAPI."""

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, cast

from deykit.api.recent import RecentProject
from deykit.application.projects import ProjectBackend

from .app import create_inner_app
from .assets import AssetCatalog
from .config import LocalServerConfig
from .dependencies import ApiDependencies
from .dto.common import Failure
from .runtime import SystemClock, new_id
from .session import SessionCapability


def _required_versions(value: Any) -> None:
    if isinstance(value, dict):
        properties = value.get("properties", {})
        if "schema_version" in properties:
            value["required"] = sorted(set(value.get("required", [])) | {"schema_version"})
        for child in value.values():
            _required_versions(child)
    elif isinstance(value, list):
        for child in value:
            _required_versions(child)


class _SchemaRecentProjects:
    last_warning: str | None = None

    def list(self) -> tuple[RecentProject, ...]:
        return ()

    def remember(self, path: str, project_id: str, name: str) -> str | None:
        return None


def _schema_dependencies() -> ApiDependencies:
    def no_source(path: Path, create: bool) -> ProjectBackend:
        raise AssertionError("schema export must not open a project")

    return ApiDependencies(
        clock=SystemClock(),
        id_factory=new_id,
        source_factory=no_source,
        recent_store=_SchemaRecentProjects(),
        demo_staging_factory=lambda: cast(ProjectBackend, None),
    )


def contract_documents() -> dict[str, bytes]:
    # Construction does not load assets, run lifespan, open folders or resolve credentials.
    config = LocalServerConfig("127.0.0.1:8765", "http://127.0.0.1:8765", AssetCatalog({}))
    app = create_inner_app(config, SessionCapability.create(), _schema_dependencies())
    openapi = app.openapi()
    failure = Failure.model_json_schema(ref_template="#/components/schemas/{model}")
    definitions = failure.pop("$defs", {})
    openapi["components"]["schemas"].update(definitions)
    openapi["components"]["schemas"]["Failure"] = failure
    openapi["components"]["schemas"].pop("HTTPValidationError", None)
    openapi["components"]["schemas"].pop("ValidationError", None)
    for path in openapi["paths"].values():
        for operation in path.values():
            for status in ("400", "403", "404", "405", "413", "414", "415", "422", "431", "500"):
                operation["responses"][status] = {
                    "description": "Safe structured failure",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Failure"}}
                    },
                }
    schemas = copy.deepcopy(openapi["components"]["schemas"])
    reference_pattern = re.compile(r"^#/components/schemas/([^/#]+)(/.*)?$")

    def fix_references(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str):
                match = reference_pattern.fullmatch(reference)
                if match is not None:
                    suffix = match[2] or ""
                    value["$ref"] = f"urn:deykit:transport:{match[1]}#{suffix.lstrip('#')}"
            for child in value.values():
                fix_references(child)
        elif isinstance(value, list):
            for child in value:
                fix_references(child)

    for name, schema in schemas.items():
        fix_references(schema)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:deykit:transport:{name}"
    documents: dict[str, bytes] = {}
    for name, value in {"openapi.json": openapi, "schemas.json": schemas}.items():
        _required_versions(value)
        documents[name] = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
    return documents


def export_contracts(destination: Path, *, check: bool = False) -> None:
    documents = contract_documents()
    if check:
        for name, body in documents.items():
            if not (destination / name).is_file() or (destination / name).read_bytes() != body:
                raise SystemExit(f"stale local API contract: {name}")
    else:
        destination.mkdir(parents=True, exist_ok=True)
        for name, body in documents.items():
            (destination / name).write_bytes(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    export_contracts(args.output, check=args.check)


if __name__ == "__main__":
    main()
