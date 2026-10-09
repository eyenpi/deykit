# CLI troubleshooting

Use `--json` to inspect a stable error code and reason without relying on terminal
wording. Parser errors, validation errors, conflicts, missing resources, and
incomplete runs have distinct exit codes and safe error envelopes. Provider
credentials and private source bodies are not included in selector alternatives.

When an exact ID is missing or ambiguous, inspect the returned top-level
`selection.choices`. Each choice includes a resource kind, exact ID, and owner
scope. A case ID must be paired with its dataset; a revision belongs to one
decision. Re-run with the returned ID and the required owning selector. Names are
never accepted in place of IDs.

For paged output, pass the returned `next_cursor` back with the same command and
limit. For report or tutorial failures, retain the project and output directory;
they contain the source and immutable evidence created before the failed step.
Validate the project before continuing:

```sh
deykit --project PATH --json project validate
deykit --project PATH --json project rebuild-index
deykit --project PATH --json project validate
```

The packaged walkthrough never retries a failed run automatically. Inspect the
reported command and its retained operation ID before choosing an explicit
recovery action.
