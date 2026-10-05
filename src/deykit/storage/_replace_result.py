"""Receipt for a completed anchored replacement and its directory flush."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class _ReplaceResult:
    parent_flush: Literal["confirmed", "unavailable", "failed"]
    post_commit_error: OSError | None
