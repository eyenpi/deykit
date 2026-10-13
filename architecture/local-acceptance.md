# Local system acceptance

The confirmed P01–P18 local browser and CLI milestone is accepted through M13.
This is local software and bounded provider compatibility evidence. CI, native
Windows and physical platform acceptance remain deferred below. Nothing was
published, released or deployed.

The accepted runtime is `e7e147c987ea20c3c55e424f42399b05a11e4258`.
The acceptance notes and screenshots added afterward change documentation only;
their final package is built and checked separately. See the
[safe machine-readable evidence](local-acceptance-evidence/qualification.json),
[CLI walkthrough](../guide/cli-workflow.md),
[browser authoring](../guide/browser-authoring.md),
[execution review](../guide/browser-execution.md), and
[debugging guide](../guide/browser-debugging.md).

## What is implemented

Portable projects contain versioned decisions, datasets, examples, labels and
fixture bindings. Execution freezes exact input, request, label and result
evidence. Bounded runs support cancellation, explicit resume and operation replay.
Saved evaluations and comparisons preserve their selected snapshots. Order
diagnostics and regression checks use shared group limits and independently
chosen acceptable answers. Annotation, report creation and historical report
downloads do not dispatch inference. The browser is bundled in the Python
package and served on loopback with scoped capabilities.

M13 also fixes a result inspector regression: request and response source
checkboxes now reveal their own source independently of structured attempt
metadata. Hiding either source clears it. Frozen snapshot validation, exact
source strings and independent API privacy flags remain intact. Both new mounted
regressions fail against the original implementation and pass against the fix.

## Actual checks and evidence reuse

All verification ran sequentially in one owner slot. Browser workers were one,
retries zero. No agent was started for final review after Ali disabled subagents.

| Gate | Actual result | Source boundary |
| --- | --- | --- |
| Clean installed CLI tutorial | 99 commands, all 8 phases, program exit 0; independent numeric and command-order/exit oracles checked | `90a930e`; Python, CLI, tutorial, locks and provider/compiler semantics unchanged afterward |
| Clean installed browser authoring | All 28 phases passed, 355.130 seconds, server exit 0 | `90a930e`; authoring components, handlers and ports unchanged afterward |
| Clean installed browser execution and inspection | All 6 phases passed, 30.482 seconds, 11 fixture dispatches, zero live dispatches, server exit 0 | Current `e7e147c` package, full lifecycle/shutdown witness passed |
| Browser comparison, diagnostics/checks, saved results and reports | Whole C09/G38/S20/R11 passes, including snapshot preservation and 320px report controls | Actual `38e075c` [M12 evidence](browser-debugging-verification.md); later production UI delta is the inspector source reveal branch, reviewed with current mounted tests and execution workflow |
| Inspector focused regressions | 8 passed, including 2 new independent request/response cases; original-source negative control caught both | Current inspector source |
| Bundled asset checks | 2 passed after the inspector rebuild | Current bundled assets |
| Security, exact JSON, offline schema, path admission, socket and process/group recovery checks | 173 passed in 63.24 seconds | All semantic Python source, package configuration and lock bytes match the recorded test baseline |
| Storage/runner/API checks | Prior 257 passed, 18 skipped | Unchanged semantic runtime; retained M12 evidence, not a fresh final suite |
| Build/static checks | Locked offline sync, Ruff, mypy, generator check, TypeScript, Vite, canonical assets and wheel/sdist build passed at their recorded source boundaries | Final inspector build includes generator/type/bundle checks; final documentation-only package is rebuilt separately |
| Clean wheel and sdist installs | Python 3.11.16, noneditable, outside checkout, spaced/non-ASCII paths; 206 package files and license bytes match | Current runtime package; installed source URI checked against the actual wheel or sdist separately |

The CLI program passed, but its original owner wrapper failed an incorrect
command inventory whitelist. The whitelist was corrected and the retained
successful program was revalidated without rerunning its 99 commands. The
original wrapper evidence remains failed. A preceding CLI attempt correctly
rejected an export through macOS's `/tmp` symlink; the accepted run used the
canonical destination. These failures are not relabelled as successful runs.

There is no fresh final full Python or frontend suite claim. Prior broad suites,
current changed-module checks and installed workflows have their own exact source
boundaries. Counts above overlap and must not be summed. Package installer
metadata contains no archive hash; actual archive hashes and installed byte
parity were verified separately.

M12's group qualification disables only an optional native diagnostic watchdog:
an earlier diagnostic helper blocked in native watchdog cancellation after the
server and worker shutdown had returned. The production application is unchanged
by that workaround. Its underlying native cause remains unproved; previous
forced shutdown attempts remain failed.

## Live provider compatibility

Exactly two authorized, separate, one-attempt Jev compatibility observations
qualified: one text case on its recorded earlier runtime, and one exact JSON
case through the current clean-installed HTTP API. The JSON source includes
`9007199254740993` and `1.2300`. The expected choice was authored independently.
The JSON run completed with one attempt, zero retries, the expected choice,
server exit 0 and a clean credential scan of project artifacts and the server
log. Both allowances are consumed; no further call or retry is authorized.

Two preceding JSON preparation failures dispatched no inference: the private
authored definition omitted its mandatory schema version. The preparation was
corrected before the final allowance was durably logged and dispatched.

These observations prove bounded compatibility for those two synthetic cases.
They do not estimate model accuracy, confidence calibration, reliability,
throughput or suitability for production workloads. Authored fixture metrics
remain software evidence.

## Review and remaining limits

The owner reviewed the final inspector change, privacy/snapshot guards, generated
asset delta and evidence map. An earlier independent Luna HIGH review applies to
its recorded `77f4f53` source. Later scoped changes received owner review only;
there is no fresh independent final-commit review, following Ali's direct
instruction to stop using subagents.

GitHub Actions is deferred under Ali's local-only gate. Native Windows install,
runtime, crash and socket checks are deferred; POSIX and static/mock checks are
not Windows execution evidence. Physical keyboard/accessibility testing, human
IME and real OS keyring interaction also remain deferred. Browser composition
tests use automated events. Qualification uses production compiler/services and
FixtureBackend, with named fake secret-store and model-listing ports where
needed; those ports do not prove real keyring or provider listing behavior.

The original checkout and ignored orchestration notes remain preserved.
Normal GitHub PR permissions apply; no branch protection or security settings
are bypassed. The paused heartbeat stays paused after local completion.

## Screenshots

These are actual headless installed-browser screenshots, inspected by the owner.
The fixture run deliberately includes cancellation and invalid/error examples;
its status and retained polling hints are part of the captured qualification.

[Frozen result inspection](local-acceptance-evidence/frozen-results-default.png)
and [320px run inspection](local-acceptance-evidence/run-narrow-320.png).
