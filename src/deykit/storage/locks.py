"""OS-held ownership, released by close/process death; timestamps never grant ownership."""

from collections.abc import Iterator
from contextlib import contextmanager

from deykit.storage.errors import fail
from deykit.storage.filesystem import SafeFiles


@contextmanager
def acquire(files: SafeFiles, name: str, *, execution: bool = False) -> Iterator[None]:
    with files.ownership(name) as acquired:
        if not acquired:
            fail(
                "execution_owned" if execution else "source_busy",
                "execution_locked" if execution else "conflict",
            )
        yield
