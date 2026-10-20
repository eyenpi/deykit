"""Short-lived directory handles and spelling inventories for ordered writes."""

from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from deykit.storage._paths import Parts
from deykit.storage.errors import fail

if TYPE_CHECKING:
    from deykit.storage._filesystem_posix import PosixFiles


@dataclass
class DirectoryFrame:
    fd: int
    parts: Parts
    names: dict[str, str | None]
    requested: dict[str, str] = field(default_factory=dict)

    def expect(self, name: str) -> None:
        folded = name.casefold()
        if self.names.get(folded, name) != name:
            fail("casefold_collision", "conflict")
        self.requested[folded] = name


class DirectoryBatch:
    """Retain only the current ancestry; re-enumerate every directory when leaving it."""

    def __init__(self, files: PosixFiles) -> None:
        self.files = files
        self.frames: list[DirectoryFrame] = []

    def __enter__(self) -> DirectoryBatch:
        self._push(os.dup(self.files.fd), ())
        return self

    def _push(self, fd: int, parts: Parts) -> None:
        try:
            names = self._spellings(fd)
        except BaseException:
            os.close(fd)
            raise
        self.frames.append(DirectoryFrame(fd, parts, names))

    @staticmethod
    def _spellings(fd: int) -> dict[str, str | None]:
        names: dict[str, str | None] = {}
        for name in os.listdir(fd):
            folded = name.casefold()
            names[folded] = None if folded in names else name
        return names

    def _finish(self) -> None:
        frame = self.frames.pop()
        try:
            names = self._spellings(frame.fd)
            for folded, requested in frame.requested.items():
                if names.get(folded, requested) != requested:
                    fail("casefold_collision", "conflict")
        finally:
            os.close(frame.fd)

    def __exit__(self, kind: object, *_: object) -> None:
        try:
            if kind is None:
                while self.frames:
                    self._finish()
        finally:
            with ExitStack() as cleanup:
                while self.frames:
                    cleanup.callback(os.close, self.frames.pop().fd)

    def parent(self, parts: Parts, *, create: bool) -> DirectoryFrame:
        while parts[: len(self.frames[-1].parts)] != self.frames[-1].parts:
            self._finish()
        for index in range(len(self.frames[-1].parts), len(parts)):
            parent = self.frames[-1]
            name = parts[index]
            parent.expect(name)
            if create:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=parent.fd)
                    os.fsync(parent.fd)
                except FileExistsError:
                    pass
            # Anchored opens reject symlinks even if a name changes after enumeration.
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent.fd)
            parent.names[name.casefold()] = name
            self._push(child, parts[: index + 1])
        return self.frames[-1]
