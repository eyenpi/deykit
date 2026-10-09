"""Explicit, narrow composition inputs for the loopback API."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from deykit.application.projects import ProjectBackend
from deykit.application.demo import DemoDestinationFactory
from deykit.contracts.ports import Clock

from .recent import RecentProject


class RecentProjects(Protocol):
    last_warning: str | None

    def list(self) -> tuple[RecentProject, ...]: ...
    def remember(self, path: str, project_id: str, name: str) -> str | None: ...


@dataclass(frozen=True)
class ApiDependencies:
    clock: Clock
    id_factory: Callable[[], str]
    source_factory: Callable[[Path, bool], ProjectBackend]
    recent_store: RecentProjects
    demo_staging_factory: Callable[[], ProjectBackend]
    demo_destination_factory: DemoDestinationFactory


ApiProjectSource = ProjectBackend
