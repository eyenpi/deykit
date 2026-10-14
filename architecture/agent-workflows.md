# Agent workflow boundary and verification

The agent interface is the repository's existing CLI. README and AGENTS direct an
arriving agent to `guide/agents.md`, locked setup and an offline console exercise.
`capabilities` exposes the installed parser rather than a second static command
schema. The committed command matrix and parameter inventory retain their
registration checks. Parser discovery does not open project/provider state;
semantic rules continue to belong to application services and feature guides.

User projects stay separate from the checkout. Stable operation IDs, reviewed
previews and exact source strings remain the workflow contracts. No new provider,
server, credential mechanism or dependency is introduced. The build remains an
internal packaging/verification mechanism; agents can use the checkout directly.

## Local evidence, 2026-10-14

Checked on macOS arm64 / Python 3.14.7 against a worktree based on
`6699840c49e494040e2cd0f0ddb6e74825372b93`. The change's pull request records final
checks and source identity.

The agent console exercise creates a fresh external project in a path with spaces
and non-ASCII characters. It checks one-request preview with no run creation,
one fixture attempt, replay preserving run identity/attempt count, missing-resource
selection, report export, project integrity and refusal to overwrite a destination.
Command discovery tests compare parser metadata with the committed inventory and
reject unknown paths without project access. This is automated software evidence,
using authored fixtures; no live model or independent human-agent adoption was
measured.

The six focused discovery/inventory/console tests passed. Ruff check and format
(338 files), mypy (185 source files), build, and 39 local documentation links
passed. Fresh locked wheel and sdist installations outside the checkout passed
version/help, exact-JSON and demo probes without credentials, PYTHONPATH or Node.
The complete eight-phase authored walkthrough passed from the installed wheel,
including comparisons, reevaluation, grouped diagnostics, regression checks and
historical report reexports. An initial cached-only installation failed because
binary dependencies were not cached; normal registry-assisted setup succeeded.
Walkthrough execution made no provider requests.

The full offline suite was interrupted after 575.51 seconds with **652 passed,
3 skipped**, while constructing the existing grouped-report fixture. The same
`tests/reports/test_cli_reports.py::test_console_exports_each_target_and_pinned_group_snapshots`
failed to complete on unchanged base main within a separate 45-second observation
and was stopped before a test result. This establishes an incomplete baseline
check, not a diagnosed runtime defect or a passing aggregate. The grouped-report
fixture and remaining full-suite coverage need a completed observation before
claiming aggregate acceptance. No runner or fixture
assertion was changed to bypass that limitation.

Native Linux/Windows, other Python versions, real provider execution and future
agent compliance are not established by these local checks. See the retained
[verification status](verification.md) for the broader platform boundaries.
