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

The initial six focused discovery/inventory/console tests passed. Ruff check and format
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
check, not a diagnosed runtime defect or a passing aggregate.

A subsequent adversarial review completed the full offline suite on the same
macOS/Python environment: **1,264 passed, 21 skipped in 1,561.85 seconds**, including
the grouped-report/resume checks. The skips cover optional cached-graph qualification,
an unavailable optional keyring package, unsupported casefold siblings and native
Windows checks. No runner or fixture assertion was changed to bypass the earlier
limitation.

Native Linux/Windows, other Python versions, real provider execution and future
agent compliance are not established by these local checks. See the retained
[verification status](verification.md) for the broader platform boundaries.

The review reproduced a quickstart failure with Windows-1252 standard output:
CLI output inherited the system encoding but was decoded as UTF-8. The quickstart
now explicitly requests UTF-8 from its CLI children and emits an ASCII JSON
summary, preserving Unicode paths. New real-console cases cover UTF-8, Windows-1252
and ASCII environments with Japanese characters, spaces and refusal to overwrite.
All eight focused discovery/inventory/console tests passed in 33.73 seconds after
the fix. Ruff check and formatting (338 files), mypy (185 source files),
package build and diff whitespace checks passed. The PR records the reviewed
source identity; its native CI matrix was still pending during local closeout.
