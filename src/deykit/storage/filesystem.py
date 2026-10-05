"""Small platform-independent facade over privately owned filesystem handles."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol

from deykit.storage._paths import Parts, check_component
from deykit.storage.errors import fail

__all__ = ["Parts", "SafeFiles"]


class _Files(Protocol):
    root: Path

    def close(self) -> None: ...
    def mkdir(self, parts: Parts) -> None: ...
    def names(self, parts: Parts) -> tuple[str, ...]: ...
    def is_directory(self, parts: Parts) -> bool: ...
    def read(self, parts: Parts, *, limit: int) -> bytes | None: ...
    def replace(self, parts: Parts, body: bytes) -> None: ...
    def unlink(self, parts: Parts) -> None: ...
    def rename_directory(self, old: Parts, new: Parts) -> None: ...
    def remove_directory(self, parts: Parts) -> None: ...
    def check_path_spelling(self, parts: Parts) -> None: ...
    def ownership(self, name: str) -> AbstractContextManager[bool]: ...


class SafeFiles:
    def __init__(self, root: Path, *, create: bool = False) -> None:
        self._backend: _Files
        if os.name == "nt":
            from deykit.storage._filesystem_windows import WindowsFiles

            self._backend = WindowsFiles(root, create=create)
        elif os.name == "posix":
            from deykit.storage._filesystem_posix import PosixFiles

            self._backend = PosixFiles(root, create=create)
        else:
            fail("unsupported_storage_platform", "preflight_failed")
        self.root = self._backend.root
        self.closed = False
        self._mutex = threading.RLock()

    def close(self) -> None:
        with self._mutex:
            if not self.closed:
                self.closed = True
                self._backend.close()

    @contextmanager
    def _access(self, parts: Parts, *, empty: bool = False) -> Iterator[_Files]:
        with self._mutex:
            # Check lifetime before even validating names or touching a recycled handle.
            if self.closed:
                fail("storage_closed", "internal_error")
            if not parts and not empty:
                fail("unsafe_source_path")
            for part in parts:
                check_component(part)
            yield self._backend

    def mkdir(self, parts: Parts) -> None:
        with self._access(parts, empty=True) as backend:
            backend.mkdir(parts)

    def names(self, parts: Parts) -> tuple[str, ...]:
        with self._access(parts, empty=True) as backend:
            return backend.names(parts)

    def is_directory(self, parts: Parts) -> bool:
        with self._access(parts) as backend:
            return backend.is_directory(parts)

    def read(self, parts: Parts, *, limit: int = 16_777_216) -> bytes | None:
        with self._access(parts) as backend:
            if limit < 0:
                fail("record_resource_limit")
            return backend.read(parts, limit=limit)

    def replace(self, parts: Parts, body: bytes) -> None:
        with self._access(parts) as backend:
            backend.replace(parts, body)

    def unlink(self, parts: Parts) -> None:
        with self._access(parts) as backend:
            backend.unlink(parts)

    def rename_directory(self, old: Parts, new: Parts) -> None:
        with self._access(old) as backend, self._access(new):
            backend.rename_directory(old, new)

    def remove_directory(self, parts: Parts) -> None:
        with self._access(parts) as backend:
            backend.remove_directory(parts)

    def check_path_spelling(self, parts: Parts) -> None:
        with self._access(parts, empty=True) as backend:
            backend.check_path_spelling(parts)

    @contextmanager
    def ownership(self, name: str) -> Iterator[bool]:
        with self._access((name,)) as backend:
            # Ownership guards retain their own handles after SafeFiles.close().
            manager = backend.ownership(name)
            acquired = manager.__enter__()
        try:
            yield acquired
        finally:
            manager.__exit__(None, None, None)
