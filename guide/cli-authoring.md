# Author decisions and examples from the CLI

Install the locked project dependencies with `uv sync --locked`, then use
`uv run deykit`. The CLI calls local Python services and opens the portable
project source directly. These authoring commands make no provider inference
request and need no browser or credential.

Put `--project PATH` and `--json` before the command. Without `--project`, the
CLI looks upward from the current directory for `deykit.project.json`; it does
not use a browser's recent project. `--help` and `--version` are plain text.
In JSON mode, each command emits one versioned object on stdout: successful
`data` plus `warnings`, or a safe `error`. A validation/conflict error exits 2.
Lists include `total` and an exclusive `next_cursor`; use `--limit` and
`--cursor` to continue. Human list output is a table with stable IDs.

```sh
uv run deykit --json init './My project' --name 'Support decisions'
uv run deykit --project './My project' --json project show
uv run deykit --project './My project' --json project validate
```

`init` creates owned source files. Its result includes the real project ID and
operation ID. It suggests `.deykit/` and `reports/` ignore entries; it does not
rewrite an existing `.gitignore`. `project rebuild-index` recreates only the
disposable SQLite index from authoritative source and history.

For an installed example, `uv run deykit --json demo ./sandbox` creates a new
portable project with 12 cases, 11 fixture bindings, and 9 authored labels.
The result reports its actual project, decision, revision, dataset, profile,
and fixture-set IDs. Its evidence mode is `authored_fixture`; creation makes
zero provider requests. The destination directory must not exist. Use the
returned IDs in subsequent commands rather than copying IDs from an example.

Create a definition file as UTF-8 text. The question and option IDs are stable
identities; changing display names should keep their IDs. This example accepts
JSON input, validates the full object, and selects only `message` as model input.
The `private_note` field remains stored with a case but is not selected.

```json
{
  "schema_version": 1,
  "input_kind": "json",
  "input_schema_source": "{\"type\":\"object\",\"required\":[\"message\"]}",
  "selected_fields": ["message"],
  "questions": [{
    "id": "route",
    "kind": "choice",
    "instructions": "Choose the support route.",
    "options": [
      {"id": "billing", "name": "Billing"},
      {"id": "technical", "name": "Technical"}
    ]
  }]
}
```

Save it as `decision.json`, then run:

```sh
uv run deykit --project './My project' --json decision create routing --name 'Routing' --file decision.json
uv run deykit --project './My project' --json decision validate routing
uv run deykit --project './My project' --json decision save routing --note 'Initial routing'
uv run deykit --project './My project' decision history routing
```

`decision create` without `--file` or `--stdin` starts an empty draft. `decision
edit` accepts exactly one of `--file`, `--stdin`, `--editor`, or
`--from-revision REVISION_ID`. Incomplete drafts remain saved and inspectable;
`save` validates before creating an immutable revision. `decision show ID` shows
the draft by default; `--revision ID` selects saved content explicitly. Use
`decision diff ID REVISION_A draft` to compare the current editor state.
`decision archive` and `decision restore` keep revisions and evidence.

For exact retry of a mutation after an uncertain result, provide a stable
`--operation-id` and the ETag preconditions from the original read. `decision
show` returns `decision.etag` and `draft.etag`; `decision save` accepts them as
`--if-decision-hash` and `--if-draft-hash`. Edits and metadata changes use
`--if-hash`. A retry with the same operation ID and original preconditions
returns the original receipt, even after later changes. Reusing the ID with
changed input conflicts. With omitted preconditions, the CLI reads current
ETags; that is convenient for one-off commands, but a later retry can conflict.

Create a dataset and one case. A case file is a UTF-8 JSON object whose
`input_source` is itself exact JSON source text. This preserves large integers
and decimals without converting them through a floating-point number.

```json
{"input_kind":"json","input_source":"{\"message\":\"Refund request\",\"private_note\":9007199254740993}"}
```

```sh
uv run deykit --project './My project' --json dataset create examples --name 'Examples'
uv run deykit --project './My project' --json case add --dataset examples --id case-1 --file case.json
uv run deykit --project './My project' case list --dataset examples
uv run deykit --project './My project' --json case show case-1 --dataset examples
```

`case edit` and `case remove` accept `--if-hash` for the case and
`--if-dataset-hash` for the aggregate. A case mutation creates a new dataset
revision. Removing a current case clears its current labels in the same
transaction and leaves historical snapshots intact.

Imports require a versioned mapping. For JSONL with an `id` field and an
`input` object, use:

```json
{"schema_version":1,"input_kind":"json","input_column":"input","id_column":"id"}
```

```sh
uv run deykit --project './My project' --json dataset import examples --format jsonl --mapping mapping.json --file rows.jsonl --decision routing --dry-run
uv run deykit --project './My project' --json dataset import examples --format jsonl --mapping mapping.json --file rows.jsonl --decision routing
```

To commit exactly the reviewed import, save the full JSON `--dry-run` output
as `import-preview.json`, then run `dataset import examples --preview
import-preview.json --operation-id IMPORT_ID`. The frozen preview carries the
source, mapping, generated case IDs, and context ETags. `--preview` excludes
source, mapping, decision, revision, and format flags. A stale preview fails
before writing; retrying a completed operation with the same preview and ID
returns its original receipt even after later edits. A fresh command without
`--preview` recomputes the preview against current state.

The preview gives stable proposed case IDs, row numbers, source lines,
exclusions, and a preview hash. Without `--skip-invalid`, any invalid row makes
the commit write nothing. With `--skip-invalid`, only valid rows commit and the
excluded rows remain in the result. Decision-aware import uses the current
draft by default; `--revision ID` explicitly chooses an immutable version.
Mapping expected-answer columns requires a selected decision. Imported labels
have `imported_unknown` provenance. `--stdin` is an alternative to `--file`,
and the two cannot be combined.

Review a case before saving an expected answer. A new manual label needs an
explicit provenance. More than one `--expected` value is an acceptable set.

```sh
uv run deykit --project './My project' --json label show case-1 --decision routing --dataset examples > review.json
uv run deykit --project './My project' --json label set case-1 --decision routing --dataset examples --expected billing --provenance human --review review.json --operation-id label-case-1
uv run deykit --project './My project' label list --decision routing --dataset examples
```

The review file freezes the input and decision/label ETags shown to the reviewer.
It makes the command retryable with the same operation ID and prevents a label
from being attached to an input changed since review. `label dispute` retains
the expectation and adds a reason. `label resolve` explicitly ends a dispute;
`label clear` removes the current expectation while keeping history.
`label list --status stale` and `--status incompatible` expose expectations
that cannot currently be scored.

`label set --file batch.json` or `--stdin` accepts an atomic batch:

```json
{
  "schema_version": 1,
  "items": [
    {"case_id": "case-1", "action": "set", "expected": ["billing"], "provenance": "human"},
    {"case_id": "case-2", "action": "clear"}
  ]
}
```

Each item can also carry the `review` object returned by `label show` to pin
its context for retries. A batch validates every item before writing any.

Preview grouped train/test assignments with `dataset split ID --dry-run`.
The default is 80% development and 20% test; ratios are exact numeric strings
and may include calibration explicitly. Assignments keep identical inputs,
groups, and derived cases together. To assign every current case manually,
pass `--assignments assignments.json` with a JSON object mapping case IDs to
`development`, `calibration`, or `test`. A conflicting or incomplete mapping
fails without writing. Applying a split creates an immutable snapshot and a
new dataset revision. Save the full JSON `--dry-run` output as
`split-preview.json`, then use `dataset split ID --preview split-preview.json
--operation-id SPLIT_ID` for a reviewed commit that can be retried after later
changes. `--preview` excludes seed, ratio, assignment, and dry-run flags.
