"""Handle-relative Windows storage; process-crash recovery on tested local NTFS.

No directory-flush equivalent is assumed. Parent guards omit delete sharing, and
remain open for the complete operation (including lock ownership).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import uuid4

from deykit.application.errors import ServiceFailure
from deykit.storage import _win32 as win
from deykit.storage._paths import Parts, check_component
from deykit.storage._tree_read import TreeReadVisitor
from deykit.storage.errors import fail


class WindowsFiles:
    def __init__(self, root: Path, *, create: bool = False) -> None:
        self.api = win.Native()
        if create:
            root.mkdir(parents=True, exist_ok=True)
        self.root = root.absolute()
        try:
            self.handle = self.api.root(self.root)
        except OSError:
            fail("project_unavailable", "not_found")
        except ServiceFailure as error:
            if error.error.reason == "unsafe_source_path":
                fail("unsafe_project_path")
            raise

    def close(self) -> None:
        self.handle.close()

    @contextmanager
    def directory(self, parts: Parts, *, create: bool = False) -> Iterator[win.Handle]:
        with ExitStack() as stack:
            current = stack.enter_context(self.api.duplicate(self.handle))
            for part in parts:
                self._check_spelling(current, part)
                current = stack.enter_context(
                    self.api.open(
                        current,
                        part,
                        directory=True,
                        access=win.DIRECTORY_ACCESS,
                        share=win.SHARE_RW,
                        disposition=win.OPEN_IF if create else win.OPEN,
                    )
                )
            yield current

    def _check_spelling(self, parent: win.Handle, name: str) -> None:
        check_component(name)
        matches = [item for item in self.api.names(parent) if item.casefold() == name.casefold()]
        if matches and matches != [name]:
            fail("casefold_collision", "conflict")

    def mkdir(self, parts: Parts) -> None:
        with self.directory(parts, create=True):
            pass

    def names(self, parts: Parts) -> tuple[str, ...]:
        try:
            with self.directory(parts) as parent:
                return self.api.names(parent)
        except FileNotFoundError:
            return ()

    def is_directory(self, parts: Parts) -> bool:
        with self.directory(parts[:-1]) as parent:
            self._check_spelling(parent, parts[-1])
            with self.api.open(parent, parts[-1], directory=None, access=0x80) as handle:
                return self.api.inspect(handle).directory

    def read(self, parts: Parts, *, limit: int = 16_777_216) -> bytes | None:
        try:
            with self.directory(parts[:-1]) as parent:
                self._check_spelling(parent, parts[-1])
                with self.api.open(parent, parts[-1]) as handle:
                    return self.api.read(handle, limit)
        except FileNotFoundError:
            return None

    def read_tree(self, parts: Parts, visitor: TreeReadVisitor, *, limit: int = 16_777_216) -> None:
        with ExitStack() as stack:
            try:
                parent = stack.enter_context(self.directory(parts))
            except FileNotFoundError:
                return
            self._walk_tree(parent, parts, visitor, limit=limit)

    def _tree_entries(self, parent: win.Handle) -> tuple[tuple[str, bool], ...]:
        entries = self.api.entries(parent)
        if len({name.casefold() for name, _ in entries}) != len(entries):
            fail("casefold_collision", "conflict")
        return entries

    def _walk_tree(
        self, parent: win.Handle, parts: Parts, visitor: TreeReadVisitor, *, limit: int
    ) -> None:
        entries = self._tree_entries(parent)
        for name, directory in entries:
            child_parts = (*parts, name)
            if not visitor.include(child_parts):
                continue
            check_component(name)
            try:
                with self.api.open(
                    parent,
                    name,
                    directory=directory,
                    access=win.DIRECTORY_ACCESS if directory else win.READ,
                    share=win.SHARE_RW if directory else win.SHARE_ALL,
                    disposition=win.OPEN,
                ) as child:
                    # Native.open freshly validates type, links, reparse and actual name.
                    visitor.validate_entry(child_parts, directory=directory)
                    if directory:
                        self._walk_tree(child, child_parts, visitor, limit=limit)
                    else:
                        visitor.accept_file(child_parts, self.api.read(child, limit))
            except FileNotFoundError:
                fail("unstable_source", "conflict")
        after = self._tree_entries(parent)
        if tuple(name for name, _ in after) != tuple(name for name, _ in entries):
            fail("unstable_source", "conflict")

    def _check_target(self, parent: win.Handle, name: str) -> None:
        self._check_spelling(parent, name)
        try:
            with self.api.open(parent, name, access=0x80):
                pass
        except FileNotFoundError:
            pass

    def replace(self, parts: Parts, body: bytes) -> None:
        with self.directory(parts[:-1], create=True) as parent:
            self._check_target(parent, parts[-1])
            with self.api.open(
                parent,
                ".tmp-" + uuid4().hex,
                access=win.WRITE | win.DELETE,
                share=0,
                disposition=win.CREATE,
            ) as temporary:
                renamed = False
                try:
                    self.api.write(temporary, body)
                    self._flush_file(temporary)
                    self.api.rename(temporary, parent, parts[-1], replace=True)
                    renamed = True
                finally:
                    if not renamed:
                        self.api.delete(temporary)

    def unlink(self, parts: Parts) -> None:
        try:
            with self.directory(parts[:-1]) as parent:
                self._check_spelling(parent, parts[-1])
                with self.api.open(parent, parts[-1], access=win.DELETE | 0x80) as handle:
                    self.api.delete(handle)
        except FileNotFoundError:
            pass

    def rename_directory(self, old: Parts, new: Parts) -> None:
        with self.directory(old[:-1]) as source, self.directory(new[:-1], create=True) as target:
            self._check_spelling(source, old[-1])
            self._check_spelling(target, new[-1])
            if new[-1] in self.api.names(target):
                fail("operation_history_conflict", "conflict")
            with self.api.open(
                source,
                old[-1],
                directory=True,
                access=win.DIRECTORY_ACCESS | win.DELETE,
                share=win.SHARE_RW,
            ) as handle:
                self.api.rename(handle, target, new[-1], replace=False)

    def remove_directory(self, parts: Parts) -> None:
        # Recursion remains anchored to the same opened directory throughout cleanup.
        with self.directory(parts[:-1]) as parent:
            self._check_spelling(parent, parts[-1])
            with self.api.open(
                parent,
                parts[-1],
                directory=True,
                access=win.DIRECTORY_ACCESS | win.DELETE,
                share=win.SHARE_RW,
            ) as handle:
                self._remove_contents(handle)
                self.api.delete(handle)

    def _remove_contents(self, parent: win.Handle) -> None:
        for name in self.api.names(parent):
            check_component(name)
            with self.api.open(
                parent,
                name,
                directory=None,
                access=win.DELETE | win.DIRECTORY_ACCESS,
                share=win.SHARE_RW,
            ) as child:
                if self.api.inspect(child).directory:
                    self._remove_contents(child)
                self.api.delete(child)

    def check_path_spelling(self, parts: Parts) -> None:
        for depth, part in enumerate(parts):
            try:
                with self.directory(parts[:depth]) as parent:
                    self._check_spelling(parent, part)
                    if part not in self.api.names(parent):
                        # Probe aliases before any journal decision; Native.open checks
                        # the actual normalized long name returned by the handle.
                        try:
                            with self.api.open(parent, part, directory=None, access=0x80):
                                pass
                        except FileNotFoundError:
                            pass
                        return
            except FileNotFoundError:
                return

    @contextmanager
    def ownership(self, name: str) -> Iterator[bool]:
        with self.directory((".deykit", "locks"), create=True) as parent:
            self._check_spelling(parent, name)
            with self.api.open(
                parent,
                name,
                access=win.READ | win.WRITE,
                share=win.SHARE_RW,
                disposition=win.OPEN_IF,
            ) as handle:
                acquired = self.api.lock(handle)
                try:
                    yield acquired
                finally:
                    if acquired:
                        self.api.unlock(handle)

    def _flush_file(self, handle: win.Handle) -> None:
        self.api.flush(handle)
