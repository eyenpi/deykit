# Foundation development

Requires Python 3.11+ and uv. Current CLI scope is `deykit --version` and
`deykit --help`; project authoring, demo, run, serve and UI commands follow in later
milestone tasks. No provider credential is needed for these checks.

```sh
uv sync --locked --python 3.11
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run python tests/check_install.py
```

Tests block socket connections and validate authored software fixtures, not model
quality. Dependency installation/build may access package registries. The install
check creates separate clean wheel/sdist environments in paths containing spaces and
non-ASCII characters, imports the installed package outside this checkout, and runs
CLI version/help with only the environment's executable directory on PATH. It needs
no Node executable. Package publication and bundled browser assets are later gates.

The `Offline foundation` CI tests Python 3.11/3.13 on Ubuntu. Its conditional frontend
job activates when frontend sources arrive, with Node 22, npm 11.19.1, unit/build/format
checks and Playwright Chromium. CI success is recorded separately from authored config.
See [contract handoff](../architecture/contracts.md) and
[verification evidence](../architecture/verification.md).
