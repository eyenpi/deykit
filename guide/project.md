# Portable projects

Use the [authoring CLI](cli-authoring.md) to create and inspect portable projects
without a browser. Python callers can also create, open, validate and snapshot
a project through injected application services:

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

`project show` is a metadata view. `project validate` checks the project
reference graph from one captured source batch and reports safe warnings for
recognized evidence that remains readable but cannot be executed. It does not
repair records. A retained-source caller can use
`ProjectService.validate_opened(source)`; that method leaves the caller's source
open on success and failure.

```sh
deykit project show
deykit project validate
deykit --json --project "/path/to/project" project validate
```

Invalid project structure returns exit code 2 with a safe error reason. Successful
JSON validation includes a `warnings` array, which is empty when no supported
legacy limitation applies.

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

The filesystem adapter has POSIX and Windows implementations. The portability CI
matrix exercises local macOS, Ubuntu and Windows Server filesystems; consult the
actual PR results before treating a platform as verified. Windows acceptance targets
local NTFS and process-crash recovery. It does not establish physical Windows 11
desktop behavior. Power-loss and OS-crash recovery ordering remain unverified on
all platforms. Use a private local project directory; network or cloud-synchronized
folders are outside this tested storage guarantee. Internal links, Windows device
names/alternate streams, and case-insensitive aliases are rejected. Spaces and
Unicode characters in your selected project root are supported by the adapters.

Storage checks:

```sh
uv run pytest tests/storage -q
uv run pytest -q
uv run ruff check .
uv run mypy
```

The [storage contract](../architecture/storage.md) describes layout, scoped identities,
recovery, execution ownership and limits for service implementers.
