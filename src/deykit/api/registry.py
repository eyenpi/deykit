"""Retained, explicitly registered project sources for one server lifetime."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from deykit.application.demo import DemoInfo, DemoService
from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectBackend, ProjectInfo, ProjectService
from deykit.contracts.errors import ServiceError

from .dependencies import ApiDependencies, ApiProjectSource


@dataclass(frozen=True)
class Registration:
    id: str
    source: ApiProjectSource
    display_path: str
    project_id: str


@dataclass(frozen=True)
class RegistrationReply:
    registration_id: str
    path: str
    info: ProjectInfo
    warnings: tuple[ServiceError, ...] = ()


def _path(value: str) -> Path:
    if (
        type(value) is not str
        or not value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value.startswith(("~", "file:"))
    ):
        raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_project_path"))
    if os.name == "nt":
        if (
            not re.fullmatch(r"[A-Za-z]:[\\/].*", value)
            or value.startswith(("\\\\", "//"))
            or "\\\\?\\" in value
            or "\\\\.\\" in value
        ):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_project_path")
            )
        if len(value) > 2 and ":" in value[2:]:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_project_path")
            )
    elif not value.startswith("/") or value.startswith("//") or "\\" in value or ":" in value:
        raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_project_path"))
    try:
        path = Path(value)
        encoded = value.encode("utf-8", errors="strict")
    except (UnicodeError, ValueError):
        raise ServiceFailure(
            ServiceError(code="validation_error", reason="invalid_project_path")
        ) from None
    if not path.is_absolute() or len(encoded) > 4096:
        raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_project_path"))
    return path


class ProjectRegistry:
    def __init__(self, dependencies: ApiDependencies, *, max_registrations: int = 32) -> None:
        self._dependencies = dependencies
        self._max = max_registrations
        self._lock = Lock()
        self._registrations: dict[str, Registration] = {}
        self._by_path: dict[str, Registration] = {}
        self._pending = 0

    def register(
        self,
        action: str,
        path_text: str,
        *,
        name: str | None,
        operation_id: str,
    ) -> RegistrationReply:
        if action not in {"open", "create"}:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="unsupported_registration_action")
            )
        if action == "create" and (name is None or not name.strip()):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_project_name")
            )
        if action == "open" and name is not None:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_project_name")
            )
        path = _path(path_text)
        with self._lock:
            existing = self._by_path.get(path_text)
            if existing is None:
                if len(self._registrations) + self._pending >= self._max:
                    raise ServiceFailure(
                        ServiceError(code="conflict", reason="registration_limit")
                    )
                self._pending += 1
        service = ProjectService(
            self._dependencies.source_factory,
            self._dependencies.clock,
            self._dependencies.id_factory,
        )
        if existing is not None:
            source = existing.source
            info = (
                service.create_in(source, name or "", operation_id)
                if action == "create"
                else service.describe(source)
            )
            registration = existing
        else:
            opened_source: ApiProjectSource | None = None
            try:
                opened_source = self._dependencies.source_factory(path, action == "create")
                info = (
                    service.create_in(opened_source, name or "", operation_id)
                    if action == "create"
                    else service.describe(opened_source)
                )
                registration = Registration(
                    self._dependencies.id_factory(),
                    opened_source,
                    path_text,
                    info.project.id,
                )
                with self._lock:
                    winner = self._by_path.get(path_text)
                    if winner is None:
                        self._registrations[registration.id] = registration
                        self._by_path[path_text] = registration
                    else:
                        registration = winner
                        opened_source.close()
            except BaseException:
                if opened_source is not None:
                    opened_source.close()
                raise
            finally:
                with self._lock:
                    self._pending -= 1
        try:
            warning = self._dependencies.recent_store.remember(
                path_text, info.project.id, info.project.name
            )
        except Exception:
            warning = "recent_projects_unavailable"
        warnings = (
            (ServiceError(code="preflight_failed", reason="recent_projects_unavailable"),)
            if warning is not None
            else ()
        )
        return RegistrationReply(registration.id, path_text, info, warnings)

    def register_demo(
        self,
        path_text: str,
        operation_id: str,
        *,
        staging_factory: Callable[[], ProjectBackend],
    ) -> tuple[RegistrationReply, DemoInfo]:
        path = _path(path_text)
        with self._lock:
            existing = self._by_path.get(path_text)
            if existing is None:
                if len(self._registrations) + self._pending >= self._max:
                    raise ServiceFailure(
                        ServiceError(code="conflict", reason="registration_limit")
                    )
                self._pending += 1
        service = DemoService(
            self._dependencies.source_factory,
            self._dependencies.clock,
            self._dependencies.id_factory,
            staging_factory=staging_factory,
        )
        if existing is not None:
            demo = service.create_in(existing.source, path, operation_id=operation_id)
            info = ProjectService(
                self._dependencies.source_factory,
                self._dependencies.clock,
                self._dependencies.id_factory,
            ).describe(existing.source)
            registration = existing
        else:
            opened: ApiProjectSource | None = None
            try:
                opened_source, demo = service._create_opened(path, operation_id=operation_id)
                opened = opened_source
                info = ProjectService(
                    self._dependencies.source_factory,
                    self._dependencies.clock,
                    self._dependencies.id_factory,
                ).describe(opened)
                if info.project.id != demo.project_id:
                    raise ServiceFailure(
                        ServiceError(code="incompatible_data", reason="invalid_demo_receipt")
                    )
                registration = Registration(
                    self._dependencies.id_factory(), opened, path_text, info.project.id
                )
                with self._lock:
                    winner = self._by_path.get(path_text)
                    if winner is None:
                        self._registrations[registration.id] = registration
                        self._by_path[path_text] = registration
                    else:
                        opened.close()
                        opened = None
                        registration = winner
                if registration.source is not opened:
                    demo = service.create_in(registration.source, path, operation_id=operation_id)
                    info = ProjectService(
                        self._dependencies.source_factory,
                        self._dependencies.clock,
                        self._dependencies.id_factory,
                    ).describe(registration.source)
            except BaseException:
                if opened is not None:
                    opened.close()
                raise
            finally:
                with self._lock:
                    self._pending -= 1
        try:
            warning = self._dependencies.recent_store.remember(
                path_text, info.project.id, info.project.name
            )
        except Exception:
            warning = "recent_projects_unavailable"
        warnings = (
            (ServiceError(code="preflight_failed", reason="recent_projects_unavailable"),)
            if warning is not None
            else ()
        )
        return RegistrationReply(registration.id, path_text, info, warnings), demo

    def require(self, registration_id: str) -> Registration:
        with self._lock:
            registration = self._registrations.get(registration_id)
        if registration is None:
            raise ServiceFailure(
                ServiceError(
                    code="not_found", reason="registration_missing", resource_id=registration_id
                )
            )
        return registration

    def list(self) -> tuple[Registration, ...]:
        with self._lock:
            return tuple(self._registrations.values())

    def close_all(self) -> None:
        with self._lock:
            registrations = tuple(self._registrations.values())
            self._registrations.clear()
            self._by_path.clear()
        for registration in registrations:
            registration.source.close()
