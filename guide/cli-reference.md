# CLI command reference

The complete command inventory and its service/verification links live in
[`architecture/cli-command-matrix.json`](../architecture/cli-command-matrix.json).
The parser-level arguments, options, aliases, types, defaults, required flags,
and numeric bounds are recorded in the
[`CLI parameter inventory`](../architecture/cli-parameter-inventory.json).
Feature guides define the meaning and accepted semantic values for those
parameters. For example, report `--target-kind` is parsed as text and then
validated against the report service's supported target kinds. Run
`deykit --help` or a group command with `--help` for the installed interface.

Use global `--project PATH` to select a portable project directly. If omitted,
Deykit searches the current directory and its parents for its project marker.
Put `--json` before the command to receive one versioned JSON envelope. Successful
commands return `data`; errors return a safe `error`, and selector failures may
include transient `selection.choices`. Choices contain exact IDs and owning scope.
They do not accept display names as aliases. A case choice is scoped to its
dataset; a revision choice is scoped to its decision.

Typer also provides root-level `--install-completion` and `--show-completion`
flags for shell completion. `--version` prints the installed version; `--help`
shows the current command interface.

List commands return `total` and `next_cursor`; request the next page with the
same command's `--cursor` and a `--limit` from 1 through 500. Fixture summaries
omit raw request bodies by default. Add `fixture show ID --request` only when the
authored request source is needed.

Commands with irreversible or repeatable mutations accept `--operation-id` for
stable replay. A replay returns the original receipt before current selector
choices are considered. Changed arguments with the same operation ID fail as a
conflict. Missing-resource alternatives are read-only, project-local, and are
attached only when an explicit exact selector fails.

`serve` optionally starts the headless loopback API. It serves no pages and
opens no browser. Use `serve --port 0` for an available port. `demo PATH` creates
an authored fixture project and exits. See the [API guide](local-api.md).
