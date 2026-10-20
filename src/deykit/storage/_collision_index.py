"""Exact logical-key prefix checks, extended only after comparing the full key set."""

from deykit.contracts.ports import ResourceKey
from deykit.storage.errors import fail
from deykit.storage.records import key_path


class CollisionIndex:
    def __init__(self) -> None:
        self.keys: set[ResourceKey] = set()
        self.prefixes: dict[tuple[str, ...], tuple[str, ...]] = {}
        self.projects = 0

    def check(self, keys: set[ResourceKey], *, publish: bool = True) -> None:
        if not publish:
            if not self.keys <= keys:
                CollisionIndex().check(keys)
                return
            prefixes: dict[tuple[str, ...], tuple[str, ...]] = {}
            projects = self.projects
            for key in keys - self.keys:
                projects += key.collection == "project"
                if projects > 1:
                    fail("project_identity_conflict", "conflict")
                path = key_path(key)
                for depth in range(1, len(path) + 1):
                    prefix = path[:depth]
                    folded = tuple(part.casefold() for part in prefix)
                    previous = prefixes.get(folded, self.prefixes.get(folded))
                    if previous is not None and previous != prefix:
                        fail("casefold_collision", "conflict")
                    prefixes[folded] = prefix
            return
        if not self.keys <= keys:
            self.clear()
        try:
            for key in keys - self.keys:
                self.projects += key.collection == "project"
                if self.projects > 1:
                    fail("project_identity_conflict", "conflict")
                path = key_path(key)
                for depth in range(1, len(path) + 1):
                    prefix = path[:depth]
                    folded = tuple(part.casefold() for part in prefix)
                    if folded in self.prefixes and self.prefixes[folded] != prefix:
                        fail("casefold_collision", "conflict")
                    self.prefixes[folded] = prefix
            if len(keys) <= 131_072:
                self.keys = set(keys)
            else:
                self.clear()
        except BaseException:
            self.clear()
            raise

    def clear(self) -> None:
        self.keys.clear()
        self.prefixes.clear()
        self.projects = 0
