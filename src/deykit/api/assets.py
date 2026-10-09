"""Serve immutable, manifest-listed package bytes only; never a project directory."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import PurePosixPath
from types import MappingProxyType

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


@dataclass(frozen=True)
class Asset:
    body: bytes
    content_type: str
    sha256: str


class AssetCatalog:
    def __init__(self, assets: Mapping[str, Asset]) -> None:
        self.assets: Mapping[str, Asset] = MappingProxyType(dict(assets))

    @classmethod
    def from_package(cls) -> "AssetCatalog":
        try:
            root = files("deykit.api").joinpath("static")
            manifest = json.loads(root.joinpath("manifest.json").read_bytes())
            if set(manifest) != {"schema_version", "assets"} or manifest["schema_version"] != 1:
                raise ValueError
            assets: dict[str, Asset] = {}
            for entry in manifest["assets"]:
                if set(entry) != {"name", "sha256", "content_type"}:
                    raise ValueError
                name = entry["name"]
                path = PurePosixPath(name)
                if (
                    not isinstance(name, str)
                    or not name.isascii()
                    or name.startswith("/")
                    or "\\" in name
                    or "%" in name
                    or ".." in path.parts
                    or str(path) != name
                    or name in assets
                ):
                    raise ValueError
                content_type = _MIME.get(path.suffix)
                if content_type is None or entry["content_type"] != content_type:
                    raise ValueError
                body = root.joinpath(name).read_bytes()
                digest = hashlib.sha256(body).hexdigest()
                if digest != entry["sha256"]:
                    raise ValueError
                assets[name] = Asset(body, content_type, digest)
            if "index.html" not in assets:
                raise ValueError
            return cls(assets)
        except (OSError, ValueError, TypeError, KeyError):
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="ui_assets_unavailable")
            ) from None
