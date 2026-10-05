"""OS-held ownership, released by close/process death; timestamps never grant ownership."""

import errno
import os
from collections.abc import Iterator
from contextlib import contextmanager

from deykit.storage.errors import fail
from deykit.storage.filesystem import SafeFiles


@contextmanager
def acquire(files: SafeFiles, name: str, *, execution: bool = False) -> Iterator[None]:
    import fcntl

    fd = files.lock_fd(name)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            fail(
                "execution_owned" if execution else "source_busy",
                "execution_locked" if execution else "conflict",
            )
        yield
    finally:
        os.close(fd)
