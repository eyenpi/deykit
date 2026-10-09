# CLI command reference

The complete command inventory and its service/verification links live in
[`architecture/cli-command-matrix.json`](../architecture/cli-command-matrix.json).
Run `deykit --help` or a group command with `--help` for live option types,
defaults, and required arguments.

Use global `--project PATH` to select a portable project directly. If omitted,
Deykit searches the current directory and its parents for its project marker.
Put `--json` before the command to receive one versioned JSON envelope. Successful
commands return `data`; errors return a safe `error`, and selector failures may
include transient `selection.choices`. Choices contain exact IDs and owning scope.
They do not accept display names as aliases. A case choice is scoped to its
dataset; a revision choice is scoped to its decision.

List commands return `total` and `next_cursor`; request the next page with the
same command's `--cursor` and a `--limit` from 1 through 500. Fixture summaries
omit raw request bodies by default. Add `fixture show ID --request` only when the
authored request source is needed.

Commands with irreversible or repeatable mutations accept `--operation-id` for
stable replay. A replay returns the original receipt before current selector
choices are considered. Changed arguments with the same operation ID fail as a
conflict. Missing-resource alternatives are read-only, project-local, and are
attached only when an explicit exact selector fails.

`serve` and `demo --open` remain planned. The CLI matrix marks those rows
explicitly; the packaged tutorial covers the available local workflow without
starting an API server or browser.
