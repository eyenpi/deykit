"""Protected atomic destination writes using the storage backends' commit receipt."""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, cast

from deykit.application.errors import ServiceFailure
from deykit.contracts.artifacts import ArtifactWriteOutcome
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.redaction import Sanitizer
from deykit.storage._filesystem_posix import PosixFiles
from deykit.storage._filesystem_windows import WindowsFiles
from deykit.storage._paths import check_component
from deykit.storage.filesystem import SafeFiles

_MANIFEST = "deykit.project.json"
_PROTECTED_DIRECTORIES = ("source", "history", ".deykit")
_DURABILITY_WARNING = ServiceError(
    code="internal_error", reason="export_durability_unverified"
)


@dataclass(frozen=True)
class _Location:
    root: str
    components: tuple[str, ...]


@dataclass
class _PosixGuard:
    location: _Location
    chain: list[int]
    nodes: dict[str, tuple[int, int] | None]
    node_fds: list[int]


@dataclass
class _WindowsGuard:
    location: _Location
    backend: WindowsFiles
    chain: list[object]
    nodes: dict[str, tuple[int, int] | None]
    node_handles: list[object]


class _Rejected(Exception):
    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason


def _failure(code: str, reason: str) -> ArtifactWriteOutcome:
    return ArtifactWriteOutcome(
        success=False,
        destination=None,
        error=ServiceError(code=cast(ErrorCode, code), reason=reason),
    )


def _invalid(reason: str = "export_destination_unsafe") -> _Rejected:
    return _Rejected("validation_error", reason)


def _location(raw: str, *, directory: bool = False) -> _Location:
    if not raw or "\x00" in raw:
        raise _invalid("invalid_artifact_input")
    try:
        raw.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise _invalid("invalid_unicode") from None

    if os.name == "posix":
        if raw.startswith("//"):
            raise _invalid("unsupported_export_root")
        if not directory and raw.endswith("/"):
            raise _invalid()
        full = raw if raw.startswith("/") else f"{os.getcwd()}/{raw}"
        components = full.split("/")[1:]
        if any(component in {"", ".", ".."} for component in components):
            raise _invalid()
        clean = tuple(components)
        if not clean:
            raise _invalid()
        for component in clean:
            try:
                check_component(component)
            except ServiceFailure:
                raise _invalid() from None
        return _Location("/", clean)

    if os.name == "nt":
        if raw.startswith(("\\\\", "//", "\\?\\", "\\.\\", "\\??\\")):
            raise _invalid("unsupported_export_root")
        if not directory and raw.endswith(("\\", "/")):
            raise _invalid()
        if not directory and raw.replace("/", "\\").rsplit("\\", 1)[-1] == ".":
            raise _invalid()
        spelling = raw.replace("/", "\\")
        raw_tail = spelling[2:] if len(spelling) >= 2 and spelling[1] == ":" else spelling
        if raw_tail.startswith("\\"):
            raw_tail = raw_tail[1:]
        if raw_tail and any(
            component in {"", ".", ".."} for component in raw_tail.split("\\")
        ):
            raise _invalid()
        path = PureWindowsPath(raw)
        if path.drive and not path.root:
            raise _invalid("unsupported_export_root")
        if not path.drive:
            if raw.startswith(("\\", "/")):
                raise _invalid("unsupported_export_root")
            path = PureWindowsPath(os.getcwd()) / path
        if not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ":":
            raise _invalid("unsupported_export_root")
        components = path.parts[1:]
        if any(component in {"", ".", ".."} for component in components):
            raise _invalid()
        clean = tuple(components)
        if not clean:
            raise _invalid()
        for component in clean:
            try:
                check_component(component)
            except ServiceFailure:
                raise _invalid() from None
        return _Location(path.drive + "\\", clean)

    raise _invalid("unsupported_export_platform")


def _service_error(failure: ServiceFailure) -> ArtifactWriteOutcome:
    reason = failure.error.reason
    if reason in {"unsafe_source_path", "unsafe_project_path", "casefold_collision"}:
        return _failure("validation_error", "export_destination_unsafe")
    if reason in {"project_unavailable", "frozen_resource_missing"}:
        return _failure("not_found", "export_parent_missing")
    return _failure("internal_error", "export_write_failed")


class NativeArtifactWriter:
    """Atomically replace a leaf after anchored path and project-protection checks."""

    def __init__(
        self,
        protected_project_roots: tuple[Path, ...] = (),
        *,
        sanitizer: Sanitizer | None = None,
    ) -> None:
        self.protected_project_roots = tuple(Path(item) for item in protected_project_roots)
        self.sanitizer = sanitizer or Sanitizer()

    def write(
        self,
        destination: str,
        body: bytes,
        *,
        display_is_safe: Callable[[str], bool] | None = None,
    ) -> ArtifactWriteOutcome:
        if type(destination) is not str or type(body) is not bytes:
            return _failure("validation_error", "invalid_artifact_input")
        try:
            self._safe_display(destination, display_is_safe)
            location = _location(destination)
            protected = tuple(
                _location(str(root), directory=True) for root in self.protected_project_roots
            )
            if os.name == "posix":
                return self._write_posix(location, protected, body, display_is_safe)
            if os.name == "nt":
                return self._write_windows(location, protected, body, display_is_safe)
            raise _invalid("unsupported_export_platform")
        except _Rejected as error:
            return _failure(error.code, error.reason)
        except ServiceFailure as failure:
            return _service_error(failure)
        except FileNotFoundError:
            return _failure("not_found", "export_parent_missing")
        except PermissionError:
            return _failure("internal_error", "export_permission_denied")
        except OSError:
            return _failure("internal_error", "export_write_failed")
        except Exception:
            return _failure("internal_error", "export_write_failed")

    def _write_posix(
        self,
        location: _Location,
        protected: tuple[_Location, ...],
        body: bytes,
        display_is_safe: Callable[[str], bool] | None,
    ) -> ArtifactWriteOutcome:
        files = SafeFiles(Path("/"))
        backend = cast(PosixFiles, files._backend)
        destination_chain: list[int] = []
        guards: list[_PosixGuard] = []
        committed = False
        outcome: ArtifactWriteOutcome | None = None
        try:
            destination_chain = self._open_posix_chain(backend, location.components[:-1])
            for project in protected:
                guards.append(self._open_posix_guard(backend, project))
            leaf = location.components[-1]
            display = "/" + "/".join(location.components)
            self._safe_display(display, display_is_safe)
            self._check_posix_protection(location, destination_chain, guards)
            backend._check_target(destination_chain[-1], leaf)

            def before_replace() -> None:
                self._recheck_posix_chain(backend, location.components[:-1], destination_chain)
                for guard in guards:
                    self._recheck_posix_guard(backend, guard)
                self._check_posix_protection(location, destination_chain, guards)
                backend._check_target(destination_chain[-1], leaf)
                self._safe_display(display, display_is_safe)

            result = backend._replace_in(
                destination_chain[-1], leaf, body, before_replace=before_replace
            )
            committed = True
            warning = (
                _DURABILITY_WARNING
                if result.parent_flush != "confirmed" or result.post_commit_error is not None
                else None
            )
            outcome = ArtifactWriteOutcome(
                success=True, destination=display, durability_warning=warning
            )
        except _Rejected as error:
            outcome = _failure(error.code, error.reason)
        except ServiceFailure as failure:
            outcome = _service_error(failure)
        except FileNotFoundError:
            outcome = _failure("not_found", "export_parent_missing")
        except PermissionError:
            outcome = _failure("internal_error", "export_permission_denied")
        except OSError:
            outcome = _failure("internal_error", "export_write_failed")
        except Exception:
            outcome = _failure("internal_error", "export_write_failed")
        close_error = self._close_posix_guards(destination_chain, guards)
        try:
            files.close()
        except OSError:
            close_error = True
        if close_error:
            if committed and outcome is not None:
                outcome = ArtifactWriteOutcome(
                    success=True,
                    destination=outcome.destination,
                    durability_warning=_DURABILITY_WARNING,
                )
            elif not committed:
                outcome = _failure("internal_error", "export_write_failed")
        return outcome or _failure("internal_error", "export_write_failed")

    @staticmethod
    def _open_posix_chain(backend: PosixFiles, components: tuple[str, ...]) -> list[int]:
        chain = [os.dup(backend.fd)]
        try:
            for component in components:
                backend._check_spelling(chain[-1], component)
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=chain[-1],
                    )
                except OSError as error:
                    if error.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise _invalid("export_destination_unsafe") from None
                    raise
                if not stat.S_ISDIR(os.fstat(child).st_mode):
                    os.close(child)
                    raise _invalid()
                chain.append(child)
            return chain
        except BaseException:
            NativeArtifactWriter._close_fds(chain)
            raise

    @staticmethod
    def _posix_identity(fd: int) -> tuple[int, int]:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise _invalid()
        return int(info.st_dev), int(info.st_ino)

    def _open_posix_guard(self, backend: PosixFiles, location: _Location) -> _PosixGuard:
        chain = self._open_posix_chain(backend, location.components)
        nodes: dict[str, tuple[int, int] | None] = {}
        node_fds: list[int] = []
        try:
            root_identity = self._posix_identity(chain[-1])
            for name in _PROTECTED_DIRECTORIES:
                nodes[name] = self._open_posix_node(backend, chain[-1], name, node_fds)
            nodes["."] = root_identity
            return _PosixGuard(location, chain, nodes, node_fds)
        except BaseException:
            self._close_fds(node_fds)
            self._close_fds(chain)
            raise

    def _open_posix_node(
        self, backend: PosixFiles, parent: int, name: str, handles: list[int]
    ) -> tuple[int, int] | None:
        backend._check_spelling(parent, name)
        try:
            fd = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
        except FileNotFoundError:
            return None
        except OSError as error:
            if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise _invalid("export_destination_protected") from None
            raise
        handles.append(fd)
        return self._posix_identity(fd)

    def _recheck_posix_chain(
        self, backend: PosixFiles, components: tuple[str, ...], original: list[int]
    ) -> None:
        current = self._open_posix_chain(backend, components)
        try:
            if tuple(self._posix_identity(fd) for fd in current) != tuple(
                self._posix_identity(fd) for fd in original
            ):
                raise _invalid("export_destination_unsafe")
        finally:
            self._close_fds(current)

    def _recheck_posix_guard(self, backend: PosixFiles, guard: _PosixGuard) -> None:
        current = self._open_posix_chain(backend, guard.location.components)
        nodes: list[int] = []
        try:
            if tuple(self._posix_identity(fd) for fd in current) != tuple(
                self._posix_identity(fd) for fd in guard.chain
            ):
                raise _invalid("export_destination_protected")
            observed = {
                name: self._open_posix_node(backend, current[-1], name, nodes)
                for name in _PROTECTED_DIRECTORIES
            }
            if observed != {name: guard.nodes[name] for name in _PROTECTED_DIRECTORIES}:
                raise _invalid("export_destination_protected")
        finally:
            self._close_fds(nodes)
            self._close_fds(current)

    @staticmethod
    def _check_posix_protection(
        location: _Location, chain: list[int], guards: list[_PosixGuard]
    ) -> None:
        destination_ids = tuple(NativeArtifactWriter._posix_identity(fd) for fd in chain)
        for guard in guards:
            protected_ids = {
                identity for identity in guard.nodes.values() if identity is not None
            }
            if any(
                identity in protected_ids - {guard.nodes["."]} for identity in destination_ids
            ):
                raise _invalid("export_destination_protected")
            root_identity = guard.nodes["."]
            for index, identity in enumerate(destination_ids):
                if identity != root_identity:
                    continue
                suffix = location.components[index:]
                if suffix and suffix[0].casefold() in {
                    item.casefold() for item in _PROTECTED_DIRECTORIES
                }:
                    raise _invalid("export_destination_protected")
                if len(suffix) == 1 and suffix[0].casefold() == _MANIFEST.casefold():
                    raise _invalid("export_destination_protected")

    @staticmethod
    def _close_fds(handles: list[int]) -> bool:
        failed = False
        for fd in reversed(handles):
            try:
                os.close(fd)
            except OSError:
                failed = True
        handles.clear()
        return failed

    def _close_posix_guards(
        self, destination_chain: list[int], guards: list[_PosixGuard]
    ) -> bool:
        failed = False
        for guard in reversed(guards):
            failed = self._close_fds(guard.node_fds) or failed
            failed = self._close_fds(guard.chain) or failed
        return self._close_fds(destination_chain) or failed

    def _write_windows(
        self,
        location: _Location,
        protected: tuple[_Location, ...],
        body: bytes,
        display_is_safe: Callable[[str], bool] | None,
    ) -> ArtifactWriteOutcome:
        from deykit.storage import _win32 as win

        native_files: dict[str, tuple[SafeFiles, WindowsFiles]] = {}

        def files_for(root: str) -> WindowsFiles:
            key = root.casefold()
            current = native_files.get(key)
            if current is None:
                files = SafeFiles(Path(root))
                current = (files, cast(WindowsFiles, files._backend))
                native_files[key] = current
            return current[1]

        backend = files_for(location.root)
        destination_chain: list[object] = []
        guards: list[_WindowsGuard] = []
        committed = False
        outcome: ArtifactWriteOutcome | None = None
        try:
            destination_chain = self._open_windows_chain(backend, location.components[:-1])
            for project in protected:
                guards.append(self._open_windows_guard(files_for(project.root), project))
            leaf = location.components[-1]
            display = self._windows_display(backend, destination_chain[-1], leaf)
            self._safe_display(display, display_is_safe)
            self._check_windows_protection(location, destination_chain, guards, backend)
            backend._check_target(cast(win.Handle, destination_chain[-1]), leaf)

            def before_replace() -> None:
                self._recheck_windows_chain(backend, location.components[:-1], destination_chain)
                for guard in guards:
                    self._recheck_windows_guard(guard.backend, guard)
                self._check_windows_protection(location, destination_chain, guards, backend)
                backend._check_target(cast(win.Handle, destination_chain[-1]), leaf)
                self._safe_display(
                    self._windows_display(backend, destination_chain[-1], leaf),
                    display_is_safe,
                )

            result = backend._replace_in(
                cast(win.Handle, destination_chain[-1]),
                leaf,
                body,
                before_replace=before_replace,
            )
            committed = True
            warning = (
                _DURABILITY_WARNING
                if result.parent_flush != "confirmed" or result.post_commit_error is not None
                else None
            )
            outcome = ArtifactWriteOutcome(
                success=True, destination=display, durability_warning=warning
            )
        except _Rejected as error:
            outcome = _failure(error.code, error.reason)
        except ServiceFailure as failure:
            outcome = _service_error(failure)
        except FileNotFoundError:
            outcome = _failure("not_found", "export_parent_missing")
        except PermissionError:
            outcome = _failure("internal_error", "export_permission_denied")
        except OSError:
            outcome = _failure("internal_error", "export_write_failed")
        except Exception:
            outcome = _failure("internal_error", "export_write_failed")
        close_error = self._close_windows_guards(destination_chain, guards)
        for files, _ in native_files.values():
            try:
                files.close()
            except OSError:
                close_error = True
        if close_error:
            if committed and outcome is not None:
                outcome = ArtifactWriteOutcome(
                    success=True,
                    destination=outcome.destination,
                    durability_warning=_DURABILITY_WARNING,
                )
            elif not committed:
                outcome = _failure("internal_error", "export_write_failed")
        return outcome or _failure("internal_error", "export_write_failed")

    @staticmethod
    def _open_windows_chain(
        backend: WindowsFiles, components: tuple[str, ...]
    ) -> list[object]:
        from deykit.storage import _win32 as win

        chain: list[object] = [backend.api.duplicate(backend.handle)]
        try:
            for component in components:
                parent = cast(win.Handle, chain[-1])
                backend._check_spelling(parent, component)
                chain.append(
                    backend.api.open(
                        parent,
                        component,
                        directory=True,
                        access=win.DIRECTORY_ACCESS,
                        share=win.SHARE_RW,
                        disposition=win.OPEN,
                    )
                )
            return chain
        except BaseException:
            NativeArtifactWriter._close_windows_handles(chain)
            raise

    def _windows_identity(self, backend: WindowsFiles, handle: object) -> tuple[int, int]:
        from deykit.storage import _win32 as win

        return backend.api.identity(cast(win.Handle, handle))

    def _open_windows_guard(
        self, backend: WindowsFiles, location: _Location
    ) -> _WindowsGuard:
        chain = self._open_windows_chain(backend, location.components)
        node_handles: list[object] = []
        try:
            root_handle = cast("Any", chain[-1])
            nodes: dict[str, tuple[int, int] | None] = {
                name: self._open_windows_node(backend, root_handle, name, node_handles)
                for name in _PROTECTED_DIRECTORIES
            }
            nodes["."] = self._windows_identity(backend, root_handle)
            return _WindowsGuard(location, backend, chain, nodes, node_handles)
        except BaseException:
            self._close_windows_handles(node_handles)
            self._close_windows_handles(chain)
            raise

    def _open_windows_node(
        self, backend: WindowsFiles, parent: object, name: str, handles: list[object]
    ) -> tuple[int, int] | None:
        from deykit.storage import _win32 as win

        native_parent = cast(win.Handle, parent)
        backend._check_spelling(native_parent, name)
        try:
            handle = backend.api.open(
                native_parent,
                name,
                directory=True,
                access=win.DIRECTORY_ACCESS,
                share=win.SHARE_RW,
                disposition=win.OPEN,
            )
        except FileNotFoundError:
            return None
        handles.append(handle)
        return backend.api.identity(handle)

    def _recheck_windows_chain(
        self, backend: WindowsFiles, components: tuple[str, ...], original: list[object]
    ) -> None:
        current = self._open_windows_chain(backend, components)
        try:
            if tuple(self._windows_identity(backend, handle) for handle in current) != tuple(
                self._windows_identity(backend, handle) for handle in original
            ):
                raise _invalid("export_destination_unsafe")
        finally:
            self._close_windows_handles(current)

    def _recheck_windows_guard(self, backend: WindowsFiles, guard: _WindowsGuard) -> None:
        current = self._open_windows_chain(backend, guard.location.components)
        nodes: list[object] = []
        try:
            if tuple(self._windows_identity(backend, handle) for handle in current) != tuple(
                self._windows_identity(backend, handle) for handle in guard.chain
            ):
                raise _invalid("export_destination_protected")
            observed = {
                name: self._open_windows_node(backend, current[-1], name, nodes)
                for name in _PROTECTED_DIRECTORIES
            }
            if observed != {name: guard.nodes[name] for name in _PROTECTED_DIRECTORIES}:
                raise _invalid("export_destination_protected")
        finally:
            self._close_windows_handles(nodes)
            self._close_windows_handles(current)

    def _check_windows_protection(
        self,
        location: _Location,
        chain: list[object],
        guards: list[_WindowsGuard],
        backend: WindowsFiles,
    ) -> None:
        destination_ids = tuple(self._windows_identity(backend, item) for item in chain)
        for guard in guards:
            protected_ids = {
                identity for identity in guard.nodes.values() if identity is not None
            }
            if any(
                identity in protected_ids - {guard.nodes["."]} for identity in destination_ids
            ):
                raise _invalid("export_destination_protected")
            root_identity = guard.nodes["."]
            for index, identity in enumerate(destination_ids):
                if identity != root_identity:
                    continue
                suffix = location.components[index:]
                if suffix and suffix[0].casefold() in {
                    item.casefold() for item in _PROTECTED_DIRECTORIES
                }:
                    raise _invalid("export_destination_protected")
                if len(suffix) == 1 and suffix[0].casefold() == _MANIFEST.casefold():
                    raise _invalid("export_destination_protected")

    @staticmethod
    def _windows_display(backend: WindowsFiles, parent: object, leaf: str) -> str:
        from deykit.storage import _win32 as win

        path = backend.api.final_path(cast(win.Handle, parent))
        if path.startswith("\\\\?\\"):
            path = path[4:]
        if len(path) < 2 or path[1] != ":":
            raise _invalid("unsupported_export_root")
        return path.rstrip("\\/") + "\\" + leaf

    @staticmethod
    def _close_windows_handles(handles: list[object]) -> bool:
        from deykit.storage import _win32 as win

        failed = False
        for handle in reversed(handles):
            try:
                cast(win.Handle, handle).close()
            except OSError:
                failed = True
        handles.clear()
        return failed

    def _close_windows_guards(
        self, destination_chain: list[object], guards: list[_WindowsGuard]
    ) -> bool:
        failed = False
        for guard in reversed(guards):
            failed = self._close_windows_handles(guard.node_handles) or failed
            failed = self._close_windows_handles(guard.chain) or failed
        return self._close_windows_handles(destination_chain) or failed

    def _safe_display(
        self, value: str, display_is_safe: Callable[[str], bool] | None
    ) -> None:
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError:
            raise _invalid("invalid_unicode") from None
        try:
            safe = display_is_safe is None or display_is_safe(value)
        except Exception:
            safe = False
        if self.sanitizer.text(value) != value or not safe:
            raise _invalid("unsafe_destination_display")
