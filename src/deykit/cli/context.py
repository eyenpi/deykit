"""One CLI project lifetime and one source/clock/id construction point."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import typer

from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectService, nearest_project
from deykit.contracts.errors import ServiceError
from deykit.storage import FileProjectSource


class SystemClock:
    def utc_now(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def monotonic(self) -> float:
        return monotonic()


def new_operation_id(value: str | None) -> str:
    return value if value is not None else uuid4().hex


@dataclass(frozen=True)
class CliState:
    explicit_project: Path | None
    json_output: bool

    def require_project(self) -> Path:
        if self.explicit_project is not None:
            return self.explicit_project
        project = nearest_project(Path.cwd())
        if project is None:
            raise ServiceFailure(ServiceError(code="not_found", reason="project_not_found"))
        return project

    @contextmanager
    def source(self) -> Iterator[FileProjectSource]:
        with FileProjectSource(self.require_project()) as source:
            yield source


def state(ctx: typer.Context) -> CliState:
    value = ctx.find_root().obj
    if not isinstance(value, CliState):
        raise RuntimeError("CLI state unavailable")
    return value


def projects_service() -> ProjectService:
    return ProjectService(
        lambda path, create: FileProjectSource(path, create=create),
        SystemClock(),
        lambda: new_operation_id(None),
    )
