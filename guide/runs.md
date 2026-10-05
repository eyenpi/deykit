# Run and recover a decision

Choose a mode explicitly. A fixture run requires an authored fixture set; a live run
requires a configured provider. The default definition is the current draft. Add
`--revision ID` to choose a saved revision.

```sh
deykit --project ./sandbox run --decision DECISION --dataset DATASET \
  --mode fixture --fixture-set FIXTURES --dry-run
deykit --project ./sandbox run --decision DECISION --dataset DATASET \
  --mode fixture --fixture-set FIXTURES --operation-id first-run
```

Preview shows selected case IDs, per-case input failures, initial request count, and
limits without starting a run. Use repeated `--case ID` and `--split development`,
`calibration`, or `test` to narrow the scope. Their intersection is shown explicitly.
Labels and case metadata never become model input.

Execution defaults to 100 lifetime attempts, concurrency 2, a 60-second aggregate
request timeout, and a 600-second scheduling window. Change these with
`--attempt-limit`, `--concurrency`, `--timeout-seconds`, and `--deadline-seconds`.
Scheduling windows accept 1–86,400 seconds. `--rate-retries 0` disables the one permitted automatic documented rate/overload retry.
All attempts, including uncertain outcomes, count toward the lifetime limit.

```sh
deykit --project ./sandbox runs list --limit 20
deykit --project ./sandbox runs show RUN_ID
deykit --project ./sandbox runs cancel RUN_ID --operation-id cancel-one
deykit --project ./sandbox runs resume RUN_ID --dry-run
deykit --project ./sandbox runs resume RUN_ID --operation-id resume-one
```

Cancellation stops scheduling and lets in-flight calls settle. Opening an interrupted
project performs no inference. Resume is explicit and retains the original definition,
cases, provider configuration, request bytes, and settings. It starts another scheduling
window of the original duration. Unknown outcomes require `--retry-unknown`; preview
them first. Such a retry may duplicate a remote call whose response was lost.

Use `--attempt-limit NEW_TOTAL` on resume to extend the total cap. It cannot reduce
the current limit or reset consumed attempts. Saved valid answers and prior result
snapshots remain available. A provider-wide failure requires a new run.

An operation ID identifies the requested action. Repeating the same start or resume
with that ID retrieves its original logical run without dispatching again. Reusing
an ID for different arguments is an error. Use a new ID for a new recovery action.
If resume reports `resume_acknowledgement_incomplete`, its acknowledgement did not
finish durably. Inspect the retained run ID, then use a new operation ID for an
explicit resume; repeating the incomplete operation cannot consume a newer cancellation.

Add the global `--json` option for one structured stdout envelope. Progress stays on
stderr. Run and resume return 4 for incomplete execution, otherwise 3 for input or
response failures, otherwise 0. An incorrect prediction alone still returns 0.
`runs show` can successfully read a failed run with exit 0. Default output excludes
raw inputs and provider request/response bodies.

The packaged Sandbox and all ordinary automated tests are authored fixture evidence.
They make no live provider calls and need no key.
