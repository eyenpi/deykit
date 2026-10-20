# Evidence reports

The Python `ReportService` saves a fixed view of a run, evaluation, comparison,
diagnostic group, or regression-check group. Later run resumes and edits to
labels, regressions, or decision drafts do not replace saved evidence. Report
creation and rendering make no provider calls. Diagnostic and check reports use
the group's pinned snapshot and create no P10 evaluations or aggregate metrics.
When a selected run result has no original evaluation, the service evaluates
the saved answers against their original labels.

Create with `ReportService.create(ReportRequest(...), operation_id=...)`. Read
the complete saved report with `read(report_id)`. Use `metadata(report_id)` or
`list(cursor=..., limit=...)` for metadata only. Render as JSON or Markdown with
`render(report_id, format="json")` or `render(report_id, format="markdown")`.
To write an existing report, call `export(report_id, format=..., destination=...,
writer=...)`; a failed destination write keeps the report available for retry.

The installed CLI exposes the same service for local exports and metadata:

```text
deykit [--project PATH] [--json] report export TARGET_ID --output FILE [--format json|markdown]
deykit [--project PATH] [--json] report export TARGET_ID --target-kind run --evaluation ID --output FILE
deykit [--project PATH] [--json] report export TARGET_ID --target-kind run --result-snapshot ID --output FILE
deykit [--project PATH] [--json] report export TARGET_ID --target-kind diagnostic --group-snapshot ID --output FILE
deykit [--project PATH] [--json] report export --report-id REPORT_ID --output FILE [--format json|markdown]
deykit [--project PATH] [--json] report show REPORT_ID
deykit [--project PATH] [--json] report list [--cursor ID] [--limit 50]
```

For a new export, pass exactly one target ID or `--report-id`. New targets can
select `--target-kind run|evaluation|comparison|diagnostic|check`, and accept
`--evaluation`, `--result-snapshot`, `--group-snapshot`, and `--operation-id`
selectors. The three independent `--include-raw-inputs`,
`--include-raw-requests`, and `--include-raw-responses` switches default off.
Saved-report exports use the frozen raw choices and reject creation selectors.
Use `--output`, `--destination`, or `-o` for the local file. JSON mode prints
one versioned envelope containing export metadata; report content is written
only to the requested file. A failed destination returns the saved report ID
and artifact metadata, prints a safe error, and exits with code 2 so the same
report can be exported again. A successful write with a durability warning
keeps exit code 0 and includes the warning in the JSON envelope or on stderr.
`report show` and `report list` return metadata only.

Group reports need an explicit target kind:

```python
ReportRequest(target_id=group_id, target_kind="diagnostic")
ReportRequest(target_id=group_id, target_kind="check", group_snapshot_id=snapshot_id)
```

Omitting `group_snapshot_id` selects the latest valid matching snapshot from a
single captured source view. A pinned snapshot keeps its original member
results across later resumes. Diagnostic reports show seed, requested and
actual option orders, the independent case denominator, and observed outcomes.
Check reports retain each original regression hash, expected and actual answer,
nullable pass state, provenance, split, and the frozen baseline reason.

Raw case inputs, prepared request bodies, and stored response material are
excluded by default. `RawChoices(inputs=True, requests=True, responses=True)`
opts into each category independently. Included values are sanitized and keep
their original and sanitized identities. The sanitizer cannot recognize
arbitrary unknown plaintext secrets.
Saved attempts currently retain response JSON source strings, so reports do not
claim opaque response-byte evidence where the saved source has none.

JSON and Markdown render the same saved report deterministically. Partial
results remain visible, fixture evidence is labelled authored software
verification material, and saved rates retain their denominators and null
reasons. Markdown puts frozen model/compiler contexts before result identities
and keeps baseline, usage, and case evidence in a fixed order. It normalizes raw
source line endings in the rendered copy while JSON preserves the saved source.

## Classification experiment preset

Use `--preset classification` on a run, evaluation or saved comparison. This
adds `classification-strict-v1` analysis to the existing frozen report; it does
not coordinate runs or call a provider. Export one saved identity in all three
formats:

```sh
deykit --project /absolute/project --json report export EVALUATION_ID \
  --preset classification --target-kind evaluation --format json \
  --operation-id classification-report-1 --output /absolute/report.json
# Take REPORT_ID from the returned data.report.report_id.
deykit --project /absolute/project --json report export --report-id REPORT_ID \
  --format markdown --output /absolute/report.md
deykit --project /absolute/project --json report export --report-id REPORT_ID \
  --format csv --output /absolute/cases.csv
```

All selected cases remain visible. An expectation applies only when its frozen
label is present and neither disputed, stale nor incompatible. Legacy question
labels do not become labels for the current question. Full-cohort strict
accuracy is correct valid answers divided by **all applicable expectations**,
including input-invalid, response-error, pending and unknown cases. Valid-answer
accuracy has its own denominator. Unlabelled and excluded expectations are
never silently counted as wrong. Provenance and individual exclusion reasons
remain in the saved evaluation and CSV.

Strict per-category precision/recall/F1 use applicable single-label expectations,
including failed/missing/unknown answers as false negatives. Acceptable sets
contribute to accuracy, but not class metrics. Existing evaluation metrics below
the preset retain their original valid-answer population. Empty denominators
are unavailable with reasons. Applicable outcomes show valid, failed (input
invalid plus response error), missing (pending) and unknown counts. Refusal count
is unavailable: current saved provider evidence has no distinct refusal status;
response errors may include refusals. The preset does not guess from response
text or salvage category choices from malformed probability vectors. Strict
failures stay failed and category-only scoring is disabled.

Comparison reports retain the existing `compatible_pairs_only` policy, paired
improvements/regressions, denominator and every exclusion bucket, including
changed inputs, question/options and expectations. Input hashes compare selected
JSON, not independently verified modality or preprocessing. Prepared-image
identities are not independently recorded by the current report contract. The
report explicitly discloses this limit; compatible cases are not evidence of a
model-only causal effect. Cohort selection does not establish representativeness.
Fixture evidence remains authored software evidence, not model-quality evidence.

Latency reuses saved nearest-rank p50/p95 over **all recorded live dispatch
durations, including retries**. Its sample count is attempts with durations, not
cases; it is neither wall-clock experiment time nor cumulative case latency.
Fixture latency and usage remain unavailable.

Optionally pass `--pricing /absolute/prices.json` when creating the preset:

```json
{
  "rates": [{
    "adapter": "jev",
    "requested_model": "jev-1.14",
    "currency": "USD",
    "input_per_million": "1.25",
    "output_per_million": "5",
    "source": "Authored example only; supply your reviewed price attribution",
    "as_of": "2026-10-20T00:00:00Z"
  }]
}
```

These are illustrative rates, not a claim about current provider pricing.
Rates must be nonnegative decimal **strings**, with at most 12 digits on either
side of the decimal point. Adapter and requested model must match exactly;
duplicate entries are rejected. Rates, currency, attribution and timestamp are
frozen into the report and operation intent. There is no network price lookup.
The token-list estimate sums reported input/output usage across dispatched
attempts, including retries. Partial usage shows a reported subtotal and unknown
attempt count; the total stays unavailable. Missing prices never mean zero.
Fixture tokens are not priced. This estimate is not billed cost and excludes
discounts or charges not represented by those two token counters. No sum across
currencies or variants is implied. Re-export uses frozen rates; changing the
price file cannot change a saved report. New pricing requires a new report and
operation ID.

CSV has one row per selected case per evaluation, including excluded/missing
cases, frozen report/evaluation/run/result/label IDs, evidence mode, status,
expectations, provenance, applicability, strict correctness, denominator and
comparison bucket. Evaluation cost totals repeat on case rows and must not be
summed across rows. Empty correctness means excluded; `false` means an applicable
case failed strict scoring. To prevent spreadsheet formula execution, cells
starting with formula/control characters are prefixed with an apostrophe; JSON
retains the exact saved display strings. CSV requires a classification preset;
raw material is never included in CSV. Saved-report exports reject `--preset`
and `--pricing`, just like other creation selectors. The Python request accepts
`preset="classification"` and `ClassificationPricing`; the headless API exposes
the same creation fields and CSV download.
