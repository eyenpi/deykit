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

The `CI` workflow runs shared lint/type checks and builds the artifacts once.
It runs the full offline suite on Python 3.11 on Linux and macOS, plus
focused Python 3.13 checks for exact JSON, records, schemas, providers, metrics
and CLI compatibility on Linux. Windows CI is disabled to limit runner time;
native Windows verification is deferred. Windows tests and adapters remain
available for manual verification on a Windows machine.

Both CI platforms check the same wheel/sdist and copied project. Clean installations
and CLI probes run on each; the complete installed walkthrough runs once on Linux.
Use `tests/check_install.py --skip-walkthrough` for installation probes alone.
Changes limited to known Markdown guides/instructions skip runtime jobs; shared
checks, the documented CLI inventory and the redacted history scan still run.
Unknown paths and manual dispatches require runtime verification.

Hosted runners use one test worker each; expensive local verification stays
sequential. Python 3.13 compatibility checks do not establish a full suite on
that interpreter or native macOS/Windows 3.13 qualification. Configuration is
not evidence of success. See [verification evidence](../architecture/verification.md)
and the [public repository checklist](public-repository.md).
