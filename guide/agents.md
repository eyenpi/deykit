# Use Deykit from an AI agent

Read [AGENTS.md](../AGENTS.md) for the operating rules. Use Deykit when a task
needs examples, typed decisions, reviewed expectations and inspectable results.
A repo checkout and shell access are enough. No private service or agent-specific
client is required. Dependency setup requires Python 3.11+, uv and cached packages
or package-registry access; execution can stay entirely offline.

## Bootstrap and discover

From the checkout:

```sh
uv sync --locked
uv run deykit --json capabilities
uv run deykit --json capabilities run
uv run deykit --json capabilities results show
uv run deykit --json capabilities dataset import
```

`capabilities` reads the installed parser without opening a project or checking
credentials. Its default catalog gives command paths as arrays, summaries and
group/command kinds. Add a command path to get positional arguments, option
aliases, defaults, required state, repeatability, choices and numeric bounds.
Group paths return their descendant catalog. An unknown path exits 2 with
`error.reason=unknown_command_path`. `interface_version` versions the discovery
data; the outer envelope has its own `schema_version`.

Parser types do not capture every service rule. For example, a string-valued
mode or report target is further validated by its service. Use the feature guides
below and `COMMAND --help`. Help/version output is plain text even with `--json`.

## First successful local workflow

```sh
uv run python guide/examples/agent-quickstart.py --output /absolute/new/agent-demo
```

This executable recipe exercises the real CLI. It discovers run parameters,
creates an authored project, takes returned IDs, lists cases, previews exactly
one request, verifies that preview created no run, executes in fixture mode,
replays the same operation without an additional attempt, inspects a result,
checks a missing selector, exports JSON and validates project integrity.
This exercise verifies the first-use path. The full-suite grouped-report/resume
check remains incomplete; see [local evidence and limitations](../architecture/agent-workflows.md).
It writes `summary.json`, `receipts.json`, `report.json` and a portable project
inside the new output directory. On interruption, inspect the retained receipts
and project; rerun the exercise with a new directory. The full demo intentionally
contains invalid input and an authored response error, so running all its cases
can correctly exit 3. The quickstart selects one valid fixture case.

From a different current directory, pin the checkout independently of the project:

```sh
uv run --directory /absolute/deykit -- deykit \
  --project /absolute/your-project --json runs list --limit 20
```

Keep user projects outside the checkout. Supply absolute file paths as well,
because `--directory` changes the process working directory. Quote paths containing
spaces. For automation use an argument array, not a shell command assembled from
untrusted text. Save stdout and stderr separately. Report destinations must avoid symlink path
components; the quickstart resolves its output directory before passing paths.

## Work on the user's actual task

| Task | Start here | Result to preserve |
| --- | --- | --- |
| Define choices or JSON answers | [Authoring](cli-authoring.md): `init`, `decision create`, `decision validate`, `decision save` | Saved revision ID and definition hashes |
| Load examples | [Imports](imports.md): `dataset create`, `dataset import --dry-run`, commit `--preview` | Reviewed preview, receipt, dataset revision |
| Review expected answers | [Labels](labels.md): `label show`, `label set --review` | Actual provenance and frozen review context |
| Exercise authored answers | [Fixtures](fixtures.md): `fixture create`, `run --mode fixture --dry-run` | Exact request bindings and explicit authored evidence |
| Evaluate a provider | [Providers](providers.md) and [runs](runs.md): configure, preview, bounded `run --mode live` | Authorized scope, limits, frozen run/result IDs |
| Compare versions or label changes | [Comparisons](comparisons.md) and [evaluations](evaluations.md) | Paired evidence, actual denominators and exclusions |
| Diagnose order effects or guard failures | [Diagnostics/regressions](diagnostics-regressions.md) | Group snapshots, frozen regressions and check outcomes |
| Deliver findings | [Reports](reports.md): `report export` | Report ID, selected snapshots, export path and evidence mode |

There is no universal provider adapter. Inspect supported profiles before assuming
an arbitrary API/model is available. Authoring a fixture requires actual authored
bindings for exact compiled requests; changing a prompt does not reuse an old
binding or produce a model answer. Use the [full offline walkthrough](cli-workflow.md)
for runnable authoring, comparison and regression examples. Do not manufacture
fixture or label evidence and describe it as observed live quality.

## Parse results and recover

A successful command emits one JSON object on stdout:

```json
{"schema_version":1,"data":{},"warnings":[]}
```

A boundary failure emits `error` instead of `data`, optionally with read-only
`selection.choices` scoped to the resource owner. Do not choose a different
resource merely to make a command succeed. Inspect the actual error code/reason.
List pages include `total` and `next_cursor`; continue the same query/filter with
the returned cursor until null. Use returned IDs rather than display names.

| Exit | Meaning | Agent action |
| --- | --- | --- |
| 0 | Command completed | Inspect data; completion does not imply a correct prediction |
| 1 | Internal error | Keep the safe error and inspect state before a retry |
| 2 | Parser, validation, conflict, credential or preflight failure | Fix the cause; reread changed state on conflict |
| 3 | Input or response failures | Inspect run/check data and failed cases |
| 4 | Incomplete execution | Inspect retained run state; preview an authorized resume |
| 5 | Regression expectation failures | Inspect check data and violated expectations |

Nonzero execution exits can carry durable evidence in `data`. `runs show` may
exit 0 while reading a failed run. Keep warnings and stderr progress with the
receipt. Never hide exclusions or call a result successful just because JSON
parsed or the process exited 0. Some service outcomes (including failed report
exports) carry `data.success=false` and a nested error; always inspect data too.

Persist an operation ID **before** starting a mutation; retain its exact arguments,
input files and original hash preconditions. Retry unchanged intent with the same
ID. For imports/splits use the full reviewed `--preview` output; for labels use the
frozen `--review` output. A new operation ID is a new action, not safe deduplication.
A conflict requires renewed review. See [runs](runs.md) for incomplete resume
acknowledgements and potentially duplicated remote calls with `--retry-unknown`.

Live model listing, network doctor checks, smoke calls, live execution and live
resume need the user's authorization. A run dry-run does not dispatch inference.
Before paid execution, inspect selected IDs and initial request count, select an
immutable decision revision, set attempt/concurrency/time limits and retry policy,
and verify credential availability via references. Never print keys. Report the
actual evidence mode, labels' provenance, eligible counts, failures and untested
assumptions. Authored fixture checks establish software behavior only.
