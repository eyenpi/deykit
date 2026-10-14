# Local development

Requires Python 3.11+ and uv. Deykit is terminal-first. There is no frontend,
Node requirement or browser launcher. The optional API is headless.

```sh
uv sync --locked --python 3.11
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run python tests/check_install.py
```

Run expensive local checks sequentially. Most tests block socket connections and use
authored software fixtures, not live inference. API socket checks allow only an
explicitly bound loopback test port. Dependency installation/build may access
package registries.

Use `tests/check_install.py --offline` when all locked dependencies/build tools
are cached. It installs both artifacts with locked runtime dependencies in fresh
spaced/non-ASCII paths, checks exact JSON, creates the authored demo, and verifies
that no UI files are shipped. The installed CLI runs outside the checkout with
no credentials, PYTHONPATH or Node. It also runs the complete authored CLI
walkthrough once from the wheel.

The consolidated `CI` workflow tests Python 3.11/3.13 on Linux, macOS and Windows.
The six native jobs use independent hosted runners in parallel, with one test
worker per runner; local verification stays sequential. It checks code, tests, portability, artifacts and
redacted history. Configuration is not evidence of hosted success. See
[verification evidence](../architecture/verification.md) and the
[public repository checklist](public-repository.md).
