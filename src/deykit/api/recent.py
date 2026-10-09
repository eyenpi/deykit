"""Bounded local recent-project preference; reads never open project paths."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from deykit.contracts.ports import Clock


@dataclass(frozen=True)
class RecentProject:
    id: str
    name: str
    path: str
    last_opened_at: str
    project_id: str


class RecentProjectsStore:
    def __init__(self, clock: Clock, path: Path | None = None) -> None:
        self._clock = clock
        self._path = path if path is not None else self._default_path()
        self.last_warning: str | None = None

    @staticmethod
    def _default_path() -> Path:
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata and Path(appdata).is_absolute():
                return Path(appdata) / "deykit" / "recent-projects.json"
            raise ValueError("APPDATA must be an absolute directory.")
        if sys_platform() == "darwin":
            return (
                Path.home() / "Library" / "Application Support" / "deykit" / "recent-projects.json"
            )
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
        return base / "deykit" / "recent-projects.json"

    def _read(self) -> tuple[RecentProject, ...]:
        self.last_warning = None
        try:
            source = self._path.read_bytes()
        except FileNotFoundError:
            return ()
        except OSError:
            self.last_warning = "recent_projects_unavailable"
            return ()
        if len(source) > 65536:
            self.last_warning = "recent_projects_unavailable"
            return ()
        try:

            def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate_recent_key")
                    result[key] = value
                return result

            document = json.loads(
                source.decode("utf-8"),
                object_pairs_hook=unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("invalid_recent_number")
                ),
            )
            if type(document) is not dict or set(document) != {"schema_version", "items"}:
                raise ValueError
            if type(document["schema_version"]) is not int or document["schema_version"] != 1:
                raise ValueError
            entries = document["items"]
            if type(entries) is not list or len(entries) > 20:
                raise ValueError
            items = []
            for item in entries:
                if type(item) is not dict or set(item) != {
                    "id",
                    "name",
                    "path",
                    "last_opened_at",
                    "project_id",
                }:
                    raise ValueError
                item_id = _string(item, "id")
                name = _string(item, "name")
                path = _string(item, "path")
                last_opened_at = _string(item, "last_opened_at")
                project_id = _string(item, "project_id")
                expected_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
                if item_id != expected_id:
                    raise ValueError
                items.append(RecentProject(item_id, name, path, last_opened_at, project_id))
            return tuple(items)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            self.last_warning = "recent_projects_unavailable"
            return ()

    def list(self) -> tuple[RecentProject, ...]:
        return self._read()

    def remember(self, path: str, project_id: str, name: str) -> str | None:
        existing = list(self._read())
        warning = self.last_warning
        identifier = hashlib.sha256(path.encode("utf-8")).hexdigest()
        item = RecentProject(identifier, name, path, self._clock.utc_now(), project_id)
        items = [item, *(entry for entry in existing if entry.id != identifier)][:20]
        document = {
            "schema_version": 1,
            "items": [entry.__dict__ for entry in items],
        }
        encoded = (
            json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        if len(encoded) > 65536:
            return "recent_projects_unavailable"
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self._path.parent, delete=False) as staged:
                staged.write(encoded)
                staged.flush()
                os.fsync(staged.fileno())
            os.replace(staged.name, self._path)
        except OSError:
            return "recent_projects_unavailable"
        return warning


def sys_platform() -> str:
    import sys

    return sys.platform


def _string(value: dict[str, object], key: str) -> str:
    item = value[key]
    if type(item) is not str or not item:
        raise ValueError("invalid_recent_field")
    return item
