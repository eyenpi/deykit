# Order diagnostics and regression checks

Use fixture mode for authored offline software checks. Fixtures bind exact request
bytes, compiler and model identity. A fixture for the original order does not supply
an answer for a reordered request: missing bindings are visible failures. Live mode
requires an explicit profile and an independently authorized bounded scope.

Place `--json --project PATH` before the command. Use existing decision, dataset and
fixture IDs returned by the authoring commands. A dry run writes nothing:

```sh
deykit --json --project "$PROJECT" diagnose choice-order \
  --decision "$DECISION_ID" --dataset "$DATASET_ID" --mode fixture \
  --fixture-set "$FIXTURE_SET_ID" --orders 4 --seed 0 --attempt-limit 40 --dry-run
```

Review expanded initial requests, independent case count, order IDs and request hashes.
The initial request total must fit the caller cap. Remove `--dry-run` and supply a unique
`--operation-id` to start. Capture `data.group.group_id` and actual member run IDs from
the returned JSON, then inspect or explicitly resume that group:

```sh
deykit --json --project "$PROJECT" diagnose show "$GROUP_ID"
deykit --json --project "$PROJECT" diagnose resume "$GROUP_ID" --operation-id "$RESUME_ID"
```

All members share the attempt cap you supplied and one scheduling deadline per segment.
Retries and unknown outcomes consume capacity. Resume retains the cap and uses the
original duration for a new segment. Add `--retry-unknown` only when deliberately choosing
a fresh attempt for ambiguous outcomes. Direct child resume/cap extension is blocked.
Cancel any member with `runs cancel "$MEMBER_RUN_ID"`; new scheduling across the group
stops once observed, while already dispatched work settles. Provider-wide failures need
a new scope. Reusing an operation ID replays its saved semantic action without new calls.

Save a regression from an actual member/run and case ID returned in results:

```sh
deykit --json --project "$PROJECT" regression add "$MEMBER_RUN_ID" "$CASE_ID" \
  --expected "$OPTION_ID_A" --expected "$OPTION_ID_B" \
  --reason 'Either stable option is acceptable for this edge case' --provenance human \
  --operation-id "$SAVE_ID"
deykit --json --project "$PROJECT" regression list --decision "$DECISION_ID"
```

Saving makes zero calls. Every acceptable ID and the reason are explicit; predictions
and current labels supply no implicit expectation. Provenance accepts `human`,
`authored_fixture`, `imported_unknown` or `model_generated`. The entire original case,
split and origin references are frozen. Editing, deleting or re-adding a current case
does not change the regression input. Legacy incomplete evidence is visible with
`executable=false` and cannot run.

```sh
deykit --json --project "$PROJECT" check --decision "$DECISION_ID" --mode fixture \
  --fixture-set "$FIXTURE_SET_ID" --regression "$REGRESSION_ID" \
  --attempt-limit 10 --operation-id "$CHECK_ID"
deykit --json --project "$PROJECT" checks show "$CHECK_GROUP_ID"
deykit --json --project "$PROJECT" checks resume "$CHECK_GROUP_ID" --operation-id "$CHECK_RESUME_ID"
deykit --json --project "$PROJECT" regression remove "$REGRESSION_ID" \
  --decision "$DECISION_ID" --operation-id "$REMOVE_ID"
```

Capture the check group ID from that check's response. Omit repeated `--regression`
selectors to check all currently visible regressions for the decision. Checks use the
current draft; `--revision` explicitly selects a saved revision. Stable IDs and the
input schema must remain compatible. A fixture set must belong to the selected original
dataset, so select a compatible subset for fixture checks spanning dataset origins.
Removal hides future selection and preserves historical check expectations/results.
Identical frozen cases share an attempt but retain separate expected sets. Conflicting
versions of the same case within one dataset fail preflight.

Check baseline is explicitly unavailable (`frozen_regression_selection`), with null
accuracy and zero support; current or test-only regression inputs are never silently
used to fit a baseline. Default output shows safe identities/provenance and semantic
outcomes. Use the explicit saved-results inspection surface when raw evidence is needed.

| Exit | Meaning |
| --- | --- |
| 0 | Completed execution/check, or successful show/list retrieval |
| 1 | Unexpected persistence/internal failure |
| 2 | Validation, preflight, incompatible selection or stale context |
| 3 | Input, fixture, provider or response failure |
| 4 | Pending, unknown, cancelled, interrupted or exhausted execution |
| 5 | Completed explicit regression expectation mismatch |

Mixed checks use precedence 4, then 3, then 5. A wrong prediction in an ordinary run
alone exits 0. A retrieved failed check still uses show/list exit 0. Order disagreement
is exploratory; authored fixture results are software-verification evidence.
