# Portable projects

Project authoring CLI integration follows P02. Python callers can already create,
open, validate and snapshot a portable project through injected application services:

```python
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from deykit.application.projects import ProjectService
from deykit.storage import FileProjectSource


class LocalClock:
    def utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def monotonic(self) -> float:
        return monotonic()


projects = ProjectService(
    lambda path, create: FileProjectSource(path, create=create),
    LocalClock(),
    lambda: uuid4().hex,
)
info = projects.create(Path("my-project"), "My project", "create-project-1")
assert projects.open(Path("my-project")).project.id == info.project.id
projects.rebuild_index(Path("my-project"))
```

Use a new operation ID for a different requested mutation; retry the same operation
ID for the same request after an uncertain interruption. Conflicts preserve your
editor/source input. Read `ServiceFailure.error` for safe code/reason information.

Back up `deykit.project.json`, `source/`, and **history/** together after closing
project processes. `history/` preserves original inputs/labels, operation replay,
immutable evidence integrity, cancellation history and recoverable transaction data.
It is essential source, not a cache. Only `.deykit/` is disposable, and it should be
removed only when no project process holds its locks. Reopen and rebuild the index
after copying the whole quiescent folder. Provider credential references do not copy
actual credentials, and opening a project makes no inference request.

The current filesystem adapter is tested on POSIX macOS/Linux CI. Windows support is
an explicit later platform gate. Do not use network filesystem locks or claim
power-loss behavior beyond the underlying OS/fsync guarantees.

Storage checks:

```sh
uv run pytest tests/storage -q
uv run pytest -q
uv run ruff check .
uv run mypy
```

The [storage contract](../architecture/storage.md) describes layout, scoped identities,
recovery, execution ownership and limits for service implementers.
