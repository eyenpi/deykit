"""Descriptor-anchored POSIX filesystem operations; no followed internal symlinks."""

from __future__ import annotations

import errno
import os
import stat
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from deykit.storage._paths import Parts, check_component
from deykit.storage._replace_result import _ReplaceResult
from deykit.storage._tree_read import TreeReadVisitor
from deykit.storage.errors import fail

if sys.platform != "win32":
    from os import O_DIRECTORY, O_NOFOLLOW, O_NONBLOCK
else:
    # Never used: constructing this private backend rejects non-POSIX hosts.
    O_DIRECTORY = O_NOFOLLOW = O_NONBLOCK = 0


def _try_lock(fd: int) -> bool:
    if sys.platform == "win32":
        fail("unsupported_storage_platform", "preflight_failed")
    else:
        import errno
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            return False


class PosixFiles:
    def __init__(self, root: Path, *, create: bool = False) -> None:
        if os.name != "posix":
            fail("unsupported_storage_platform", "preflight_failed")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            fail("unsafe_project_path")
        try:
            self.fd = os.open(root, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
        except OSError:
            fail("project_unavailable", "not_found")
        self.root = root.resolve()
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            os.close(self.fd)

    @contextmanager
    def directory(self, parts: Parts, *, create: bool = False) -> Iterator[int]:
        if self.closed:
            fail("storage_closed", "internal_error")
        fd = os.dup(self.fd)
        try:
            for part in parts:
                check_component(part)
                self._check_spelling(fd, part)
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW, dir_fd=fd)
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
            self._check_spelling(parent, parts[-1])
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                fail("unsafe_source_path")
            return stat.S_ISDIR(info.st_mode)

    def read(self, parts: Parts, *, limit: int = 16_777_216) -> bytes | None:
        try:
            with self.directory(parts[:-1]) as parent:
                self._check_spelling(parent, parts[-1])
                fd = os.open(parts[-1], os.O_RDONLY | O_NOFOLLOW | O_NONBLOCK, dir_fd=parent)
                try:
                    return self._read_open_file(fd, limit=limit)
                finally:
                    os.close(fd)
        except FileNotFoundError:
            return None

    @staticmethod
    def _read_open_file(fd: int, *, limit: int) -> bytes:
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

    def read_tree(self, parts: Parts, visitor: TreeReadVisitor, *, limit: int = 16_777_216) -> None:
        # Only a missing initial prefix is optional. A missing listed child conflicts.
        with ExitStack() as stack:
            if self.closed:
                fail("storage_closed", "internal_error")
            current = os.dup(self.fd)
            stack.callback(os.close, current)
            try:
                for part in parts:
                    check_component(part)
                    self._check_spelling(current, part)
                    current = os.open(part, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW, dir_fd=current)
                    stack.callback(os.close, current)
            except FileNotFoundError:
                return
            except OSError as error:
                if error.errno in (errno.ELOOP, errno.ENOTDIR):
                    fail("unsafe_source_path")
                raise
            self._walk_tree(current, parts, visitor, limit=limit)

    @staticmethod
    def _tree_names(parent: int) -> tuple[str, ...]:
        names = tuple(sorted(os.listdir(parent)))
        if len({name.casefold() for name in names}) != len(names):
            fail("casefold_collision", "conflict")
        return names

    def _walk_tree(
        self, parent: int, parts: Parts, visitor: TreeReadVisitor, *, limit: int
    ) -> None:
        names = self._tree_names(parent)
        for name in names:
            child_parts = (*parts, name)
            if not visitor.include(child_parts):
                continue
            check_component(name)
            try:
                hint = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISLNK(hint.st_mode):
                    fail("unsafe_source_path")
                directory = stat.S_ISDIR(hint.st_mode)
                flags = os.O_RDONLY | O_NOFOLLOW | (O_DIRECTORY if directory else O_NONBLOCK)
                child = os.open(name, flags, dir_fd=parent)
                try:
                    info = os.fstat(child)
                    if directory:
                        if not stat.S_ISDIR(info.st_mode):
                            fail("unsafe_source_path")
                    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        fail("unsafe_source_path")
                    visitor.validate_entry(child_parts, directory=directory)
                    if directory:
                        self._walk_tree(child, child_parts, visitor, limit=limit)
                    else:
                        visitor.accept_file(child_parts, self._read_open_file(child, limit=limit))
                finally:
                    os.close(child)
            except OSError as error:
                if error.errno == errno.ELOOP:
                    fail("unsafe_source_path")
                if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.EISDIR):
                    fail("unstable_source", "conflict")
                raise
        if self._tree_names(parent) != names:
            fail("unstable_source", "conflict")

    def replace(self, parts: Parts, body: bytes) -> None:
        with self.directory(parts[:-1], create=True) as parent:
            self._check_target(parent, parts[-1])
            result = self._replace_in(parent, parts[-1], body)
            if result.post_commit_error is not None:
                raise result.post_commit_error

    def _replace_in(
        self,
        parent: int,
        name: str,
        body: bytes,
        *,
        before_replace: Callable[[], None] | None = None,
    ) -> _ReplaceResult:
        temporary = ".tmp-" + uuid4().hex
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        committed = False
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                written = stream.write(body)
                if written != len(body):
                    raise OSError("Storage write made no progress")
                stream.flush()
                self._flush_file(fd)
            if before_replace is not None:
                before_replace()
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            committed = True
        except BaseException:
            if not committed:
                try:
                    os.close(fd)
                except OSError:
                    pass
                try:
                    os.unlink(temporary, dir_fd=parent)
                except OSError:
                    pass
            raise

        post_commit_error: OSError | None = None
        parent_flush: Literal["confirmed", "failed"] = "confirmed"
        try:
            os.fsync(parent)
        except OSError as error:
            parent_flush = "failed"
            post_commit_error = error
        try:
            os.close(fd)
        except OSError as error:
            if post_commit_error is None:
                post_commit_error = error
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        except OSError as error:
            if post_commit_error is None:
                post_commit_error = error
        return _ReplaceResult(parent_flush, post_commit_error)

    @staticmethod
    def _check_spelling(parent: int, name: str) -> None:
        check_component(name)
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
        PosixFiles._check_spelling(parent, name)
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
            self._check_spelling(source, old[-1])
            self._check_spelling(target, new[-1])
            if not self.is_directory(old):
                fail("unsafe_source_path")
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
                name, os.O_RDWR | os.O_CREAT | O_NOFOLLOW | O_NONBLOCK, 0o600, dir_fd=parent
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                os.close(fd)
                fail("unsafe_lock_path")
            try:
                os.fsync(parent)
            except BaseException:
                os.close(fd)
                raise
            return fd

    @contextmanager
    def ownership(self, name: str) -> Iterator[bool]:
        fd = self.lock_fd(name)
        try:
            yield _try_lock(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _flush_file(fd: int) -> None:
        os.fsync(fd)
