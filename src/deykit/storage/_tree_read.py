"""Synchronous policy callbacks for one independently anchored storage walk."""

from typing import Protocol

from deykit.storage._paths import Parts


class TreeReadVisitor(Protocol):
    def include(self, parts: Parts) -> bool: ...
    def validate_entry(self, parts: Parts, *, directory: bool) -> None: ...
    def accept_file(self, parts: Parts, body: bytes) -> None: ...
