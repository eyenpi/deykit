"""Exact path selection for an independently anchored batch read."""

from deykit.storage._paths import Parts, check_component
from deykit.storage.errors import fail

FileChanges = tuple[tuple[Parts, bytes | None], ...]


class SelectedFiles:
    def __init__(self, paths: tuple[Parts, ...]) -> None:
        self.paths = set(paths)
        self.children: dict[Parts, dict[str, str]] = {}
        self.bodies: dict[Parts, bytes] = {}
        for path in paths:
            if not path:
                fail("unsafe_source_path")
            for index, name in enumerate(path):
                check_component(name)
                children = self.children.setdefault(path[:index], {})
                prior = children.setdefault(name.casefold(), name)
                if prior != name:
                    fail("casefold_collision", "conflict")
        if self.paths.intersection(self.children):
            fail("unsafe_source_path")

    def include(self, parts: Parts) -> bool:
        requested = self.children.get(parts[:-1], {}).get(parts[-1].casefold())
        if requested is not None and requested != parts[-1]:
            fail("casefold_collision", "conflict")
        return requested is not None

    def validate_entry(self, parts: Parts, *, directory: bool) -> None:
        if directory == (parts in self.paths):
            fail("unsafe_source_path")

    def accept_file(self, parts: Parts, body: bytes) -> None:
        self.bodies[parts] = body
