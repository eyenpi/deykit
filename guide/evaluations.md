# Inspecting saved results

Use a run ID returned by `deykit run`. Inspection reads the run's latest immutable result snapshot unless you select an earlier evaluation ID. It does not start or resume a run.

```console
deykit --project ./Sandbox results list RUN_ID
deykit --project ./Sandbox results list RUN_ID --status valid --split development
deykit --project ./Sandbox results show RUN_ID CASE_ID --attempts
deykit --project ./Sandbox results show RUN_ID CASE_ID --request --response
deykit --project ./Sandbox results annotate RUN_ID CASE_ID --note "Review this answer"
deykit --project ./Sandbox reevaluate RUN_ID
```

Add `--json` before the command for one versioned JSON response. `results list` reports all selected statuses and the filtered count separately. A filter with no matches returns zero filtered cases while preserving the run's selected and status counts. Use `--cursor` and `--limit` to page deterministically. `results show` displays the saved answer, expected option IDs, correctness or exclusion reasons, label provenance, probabilities, and native confidence when present. `--attempts` shows bounded retry states and hashes. `--request` and `--response` explicitly reveal sanitized raw bodies; they are omitted by default. Credential fields and Bearer tokens are redacted, and project credentials are never resolved for inspection. User input source is not shown by these commands.

`results annotate` creates an append-only note against one run and case. Supply exactly one of `--note`, `--file`, or `--stdin`. Use `--operation-id` to retry an uncertain save without creating another note. A note never changes an answer, label, or evaluation.

`reevaluate` copies the run's current decision-specific labels into a new immutable snapshot, then scores its saved answers. It makes zero provider requests and returns the new evaluation, result, and label snapshot IDs. `--result-snapshot ID` chooses an earlier saved answer snapshot. Later label edits or a resumed run cannot change an earlier evaluation; inspect one with `results list RUN_ID --evaluation EVALUATION_ID` or `results show RUN_ID CASE_ID --evaluation EVALUATION_ID`. A changed input hash, disputed label, retired question, or missing option remains visible as an exclusion rather than becoming a guessed expectation.

Accuracy means applicable labelled valid answers correct over applicable labelled valid answers. Coverage means valid answers over all selected cases. Acceptable sets count for correctness but do not enter the single-label confusion matrix or per-class F1. Undefined rates show a null value, counts, and a reason. The majority baseline fits only the run's separately frozen full development labels and scores the same eligible answers as accuracy; it reports fitting support and overlap. Fixture outputs are authored examples, not measured provider quality. Fixture duration and usage are absent. Live duration includes only recorded fresh dispatches; missing native usage and cost remain unknown.
