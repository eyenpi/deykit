# M10 integration verification — 2026-10-11

This is local integration evidence for `codex/m10-browser-authoring`, not a claim
that this PR has been merged or that the hosted CI/platform gates passed. Main
already received the M10 implementation through PR #48 during this session.
The initial main head `fc3d2fb` was already an ancestor. A normal merge pull of
origin M10 preserved both the local authoring fixes and merged PR #47, producing
`22cf7d9`. Merging `origin/main` then reported already up to date. No rebase or
force push was used.

While checks ran, PR #48 merged the M10 implementation into main, advancing it
to `d35d188`. A second normal merge produced `d82365f`. Conflicts were resolved
by preserving main's stronger archive receipt adoption, page-lifetime ownership,
navigation-before-refresh ordering, and shared provider/fixture browser tail.
The earlier effect-based local repair was superseded by those main fixes. The
remaining diff to main adds the two regression tests, a confirmed overview
screenshot capture, the shell reload and resize-readiness oracle corrections,
and this evidence.

## Integration repair

After a lost archive/restore response, an acknowledged exact retry previously
called the parent navigation callback before React published the confirmed state
to the dirty guard. The parent could remove the active decision before overview
navigation was admitted. An initial local fix deferred the callback until guard registration.
The subsequent
main merge superseded that fix with receipt adoption and a guard reading current
request refs before navigation. Two retained regressions cover archive and restore,
unknown-outcome unload protection, identical retry bodies, and admitted overview
navigation. Reintroducing the original callback made both regressions fail.

The earlier installed suite also contained stale navigation names, an incorrect
reload-route expectation, and a Tab oracle that treated normal departure from the
document as hidden focus. Main now supplies corrected shared navigation and demo
readiness controls, and checks mobile menu focus/Tab/Escape explicitly. The remaining
shell reload correction asserts restored Sandbox first, then Welcome after the
Projects action. The mobile keyboard test waits two animation frames for resize
listeners/rendering before opening Menu; its focus/Tab/Escape assertions remain.
Final production assets match main and the canonical bundle check.

## Commands and results

Commands ran serially in the assigned worktree. Python checks, frontend
tests/checks, package checks and browser checks were
repeated after the `d82365f` merge. Dependency installation preceded that merge;
the frontend lockfile did not change. The final installed run includes the
subsequent test-only reload/resize fixes. Python commands used
`UV_CACHE_DIR=/private/tmp/deykit-m10-integration-uv-cache`. The machine was macOS
arm64 with Python 3.14.7, Node 26.11.1, npm 11.20.0, and Chromium 153.0.8010.12.
Frontend commands ran from `frontend/`.

| Command | Local result |
| --- | --- |
| `uv sync --locked` | Passed |
| `nice -n 10 uv run pytest` | 1,208 passed, 21 skipped; 2,063.10 seconds |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed, 340 files |
| `uv run mypy` | Passed, 183 source files |
| `uv run python -m deykit.api.schema --check --output frontend/api-contracts` | Passed |
| `npm ci --no-audit --no-fund` | Passed |
| `npm test -- --maxWorkers=1` | 121 passed, 16 files |
| `npm run test:contracts` | 12 passed |
| `npm run typecheck` | Passed |
| `npm run format:check` | Passed |
| `npm run build` | Passed; includes API generation check and TypeScript |
| `uv run python scripts/bundle-ui.py --check` | Passed after canonical regeneration |
| `uv run pytest tests/api/test_schema_assets.py tests/cli/test_serve.py tests/api/test_socket.py` | 11 passed after UI rebuild |
| `uv build` | Wheel and sdist passed |
| `uv run python tests/check_install.py` | Both fresh wheel/sdist installations passed outside checkout in spaced/non-ASCII paths, CLI without Node on PATH |
| `nice -n 10 npm run test:browser -- --workers=1 --output=/private/tmp/deykit-m10-post-main-shell` | 6 passed |
| `npm run test:browser:installed -- --workers=1 --output=/private/tmp/deykit-m10-post-main-final/browser` | 4 passed, 7.5 minutes; all 28 connected authoring phases completed |
| `git diff --check` | Passed |

The full Python suite ran on merged baseline `22cf7d9`. Subsequent changes
included the frontend repair, frontend tests, generated assets,
main integration, and this evidence. The final tracked Python code, Python tests,
`pyproject.toml`, and `uv.lock` are identical to that full-suite baseline. The
asset/serve/socket tests and clean
package checks were repeated after the UI rebuild; the table does not imply a
second full Python run on the final integration commit.

For the installed suite, a fresh virtual environment installed the built wheel
outside checkout. Installed imports were isolated, and all 204 wheel files matched
the installation. The tracked `tests/verification/m10_installed_api_server.py`
helper ran with that installed Python using `-I`, an isolated workspace, and a
real loopback API origin supplied via `DEYKIT_INSTALLED_API_URL`. It uses authored
model listing and a fake secret-store port. Test-side Python oracles used the
installed virtual environment first on PATH.
No live credentials or inference were used. The installed server itself was not
tested with Node absent from PATH.

The installed tests cover revision restore after Back/unknown outcome,
the shared archive/provider/fixture/mobile tail, shell response-loss/reload/recent-
project safety, and the connected authoring flow.
The final suite passed all four tests. The connected flow exercises exact decision
source, imports, labels, case edits,
splits, archive/restore, provider setup, fixtures, and 320px/reduced-motion controls.
The copied progress file lists injected failure responses; these are deliberate
recovery scenarios, not unexpected failures in the passing run.

Shutdown evidence confirms revoked capabilities, an empty registry, idle workers
and supervisor, completed lifespan shutdown, zero provider dispatch and per-case
calls, and no `JEV_API_KEY`.

## Screenshots and witnesses

These headless Chromium captures were inspected visually:

- [Confirmed restored decision in overview](browser-authoring-evidence/archive-restore-confirmed-overview.png)
- [Fixture library at 320px](browser-authoring-evidence/authoring-narrow-320.png)
- [28-phase browser progress](browser-authoring-evidence/authoring-progress.json)
- [Installed server shutdown witness](browser-authoring-evidence/shutdown.json)

The narrow fixture table fits without horizontal page overflow, but long hashes
and identifiers wrap heavily. This is a readability limitation, not a claim of
physical-device or accessibility acceptance.

## Known limitations and earlier failures

- GitHub CI is blocked by account billing/spending limits. A failed check annotation
  reports that the job did not start. Local checks do not replace the configured
  Linux/macOS/Windows and Python 3.11/3.13 matrix.
- The recent PR #47 session documented broader installed-workflow failures: a
  registration read returned 409 and case-refresh recovery timed out. Those failed
  artifacts remain failures. They did not recur in the final four-test passing
  run here, which does not establish timing reliability across repeated runs or
  platforms.
- PR #48 accepted a composite 20-phase plus shared-tail gate; its earlier
  monolithic workflow remained failed. That evidence is not relabeled by this PR.
- Earlier integration attempts here failed on the archive navigation race and
  stale browser assertions. One intermediate attempt was deliberately interrupted
  after discovering further stale selectors. The first post-main run also failed
  the stale shell reload expectation and mobile menu focus after resize. Only the
  final complete run is a whole-workflow pass; none of the earlier failed or
  interrupted runs is relabeled.
- The inherited M09 controls qualification scripts had failed assertions and were
  reconciled with supplemental reads/static review; those original scripts were
  not rerun as part of this integration.
- Physical IME, keyboard and screen-reader acceptance, native Windows, real OS
  credential storage, and live Jev/provider validation remain unverified. Automated
  composition events, authored fixture answers, fake ports, and loopback tests are
  software evidence only.
- Vite still warns about the approximately 2 MB JavaScript chunk. No startup or
  performance acceptance is claimed.
- Execution/progress/results/comparison/reevaluation/diagnostic/report browser UI
  remains later M11/M12 work. Existing tracking issues #9, #16, #17, #18 and #19
  retain live-provider, broader acceptance, packaging/platform and milestone gates.
- There was no new independent review of the final integration head in this
  session. Earlier review and PR #47 evidence are retained, but are not a fresh
  final-head review. This PR must remain unmerged for review.
