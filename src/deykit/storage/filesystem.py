"""Descriptor-anchored POSIX filesystem operations; no followed internal symlinks."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from deykit.storage.errors import fail

Parts = tuple[str, ...]


class SafeFiles:
    def __init__(self, root: Path, *, create: bool = False) -> None:
        if os.name != "posix":
            fail("unsupported_storage_platform", "preflight_failed")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            fail("unsafe_project_path")
        try:
            self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            fail("project_unavailable", "not_found")
        self.root = root.resolve()
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            os.close(self.fd)
            self.closed = True

    @contextmanager
    def directory(self, parts: Parts, *, create: bool = False) -> Iterator[int]:
        fd = os.dup(self.fd)
        try:
            for part in parts:
                if not part or part in {".", ".."} or "/" in part or "\\" in part:
                    fail("unsafe_source_path")
                self._check_spelling(fd, part)
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    def mkdir(self, parts: Parts) -> None:
        with self.directory(parts, create=True):
            pass

    def names(self, parts: Parts) -> tuple[str, ...]:
        try:
            with self.directory(parts) as fd:
                return tuple(sorted(os.listdir(fd)))
        except FileNotFoundError:
            return ()

    def is_directory(self, parts: Parts) -> bool:
        with self.directory(parts[:-1]) as parent:
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                fail("unsafe_source_path")
            return stat.S_ISDIR(info.st_mode)

    def read(self, parts: Parts, *, limit: int = 16_777_216) -> bytes | None:
        try:
            with self.directory(parts[:-1]) as parent:
                self._check_spelling(parent, parts[-1])
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        fail("unsafe_source_path")
                    if info.st_size > limit:
                        fail("record_resource_limit")
                    with os.fdopen(fd, "rb", closefd=False) as stream:
                        body = stream.read(limit + 1)
                    if len(body) > limit:
                        fail("record_resource_limit")
                    return body
                finally:
                    os.close(fd)
        except FileNotFoundError:
            return None

    def replace(self, parts: Parts, body: bytes) -> None:
        with self.directory(parts[:-1], create=True) as parent:
            self._check_target(parent, parts[-1])
            temporary = ".tmp-" + uuid4().hex
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(fd)
                os.replace(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                os.close(fd)
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _check_spelling(parent: int, name: str) -> None:
        matches = [item for item in os.listdir(parent) if item.casefold() == name.casefold()]
        if matches and matches != [name]:
            fail("casefold_collision", "conflict")

    def check_path_spelling(self, parts: Parts) -> None:
        """Check existing parents and leaf, including empty directories, before staging."""
        for depth, part in enumerate(parts):
            try:
                with self.directory(parts[:depth]) as parent:
                    self._check_spelling(parent, part)
                    if part not in os.listdir(parent):
                        return
            except FileNotFoundError:
                return

    @staticmethod
    def _check_target(parent: int, name: str) -> None:
        SafeFiles._check_spelling(parent, name)
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            fail("unsafe_source_path")

    def unlink(self, parts: Parts) -> None:
        try:
            with self.directory(parts[:-1]) as parent:
                self._check_target(parent, parts[-1])
                try:
                    os.unlink(parts[-1], dir_fd=parent)
                    os.fsync(parent)
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass

    def rename_directory(self, old: Parts, new: Parts) -> None:
        with self.directory(old[:-1]) as source, self.directory(new[:-1], create=True) as target:
            if new[-1] in os.listdir(target):
                fail("operation_history_conflict", "conflict")
            os.rename(old[-1], new[-1], src_dir_fd=source, dst_dir_fd=target)
            os.fsync(source)
            os.fsync(target)

    def remove_directory(self, parts: Parts) -> None:
        # Only uncommitted staging; no recursive deletion through symlinks.
        for name in self.names(parts):
            child = (*parts, name)
            if self.is_directory(child):
                self.remove_directory(child)
            else:
                self.unlink(child)
        with self.directory(parts[:-1]) as parent:
            os.rmdir(parts[-1], dir_fd=parent)
            os.fsync(parent)

    def lock_fd(self, name: str) -> int:
        with self.directory((".deykit", "locks"), create=True) as parent:
            self._check_spelling(parent, name)
            fd = os.open(
                name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                os.close(fd)
                fail("unsafe_lock_path")
            os.fsync(parent)
            return fd
