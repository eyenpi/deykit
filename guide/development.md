# Local development

Requires Python 3.11+ and uv. The local CLI includes project authoring, the
authored fixture demo, and the loopback browser workspace. The demo and workspace
need no provider credential; `demo --open` starts the workspace after successful
demo creation.

```sh
uv sync --locked --python 3.11
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run python tests/check_install.py
```

Most tests block socket connections and validate authored software fixtures, not
model quality. Focused API and installed-browser qualification uses explicit local
loopback sockets. Dependency installation/build may access package registries.

The `Offline foundation` CI tests Python 3.11/3.13 on Ubuntu. Its conditional frontend
job activates when frontend sources arrive, with Node 22, npm 11.19.1, unit/build/format
checks and Playwright Chromium. CI success is recorded separately from authored config.
See [contract handoff](../architecture/contracts.md) and
[verification evidence](../architecture/verification.md).
