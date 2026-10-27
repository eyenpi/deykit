# Evidence reports

Managed images selected by a decision appear in evaluation reports as named
source/prepared identities, dimensions, formats and preparation settings. JSON,
Markdown and classification CSV retain the same asset IDs without including image
bytes or filesystem paths. Paired comparisons classify a changed selected image
or preparation policy as `changed_input`, excluding it from identical-input quality
counts even when the original image and labels are unchanged. Unselected dataset
images are not presented as model inputs. See [managed imports](imports.md).

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

Use `--preset classification` on a run, evaluation or saved comparison. A run
or evaluation uses `classification-strict-v2`; a comparison uses
`classification-strict-v3` and adds the experimental paired analysis described
below. Neither report coordinates runs or calls a provider. Export one saved
identity in all three formats:

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
invalid plus response error), missing (pending) and unknown counts.

The refusal count includes applicable response errors with the saved error code
`response_invalid` and reason `provider_refusal`. The OpenAI adapter records this
marker for explicit refusal answers. Refusals remain a subset of failed answers,
so they stay in the strict accuracy denominator and must not be added to failures
again. `refusal_reason=explicit_provider_refusals_only` describes the count's
scope. Zero means no explicit markers, not proof that no refusal occurred.
Other response errors may include unmarked refusals. Reports do not infer
refusals from raw response text or salvage choices from malformed probability
vectors. Category-only scoring stays disabled.

Saved v1 and v2 reports keep their original interpretation, hashes, replay and
export columns. A new comparison report and operation ID select v3. Older builds
cannot read v3 reports; retain the project and use a compatible reader when
those reports are present.

### Experimental paired comparisons

The existing `compatible_pairs_only` results and their exclusion buckets remain
unchanged. The separate `matching_labels_allow_changed_inputs_v1` section can
pair cases even when inputs or selected images differ. It requires the same case
ID, question ID and set of option IDs, the same applicable expected option IDs,
and a valid answer on each side. It excludes missing cases, changed question or
option IDs, changed expectations, invalid, incompatible or missing answers and
inapplicable expectations. Its improvements, regressions and correct counts use
only those paired valid answers. They do not use the full-cohort strict accuracy
denominator.
Different instructions or option descriptions may share IDs, so the report also
states whether the frozen definition changed.

Treatment counts cover every case ID present on both sides, including excluded
pairs, and can overlap. The report compares case input identities, prepared
request byte hashes, image presence, and selected image names and order. For
image names selected on both sides, it also compares source hashes, prepared
hashes and preparation settings. Added or removed image names appear in the
selection count rather than the shared-image counts. Unavailable request hashes
have their own count. The JSON and CSV include each case's pair bucket and
treatment flags; the Markdown report shows aggregate counts. CSV has one row
per case per evaluation, so shared cases appear twice. Filter to
`experimental_pair_row=true` to count each pair or one-sided case once. The
marked row comes from the first evaluation when that case is present, otherwise
from the second.

A case input identity covers the original case input and source images, including
images a decision did not select. Equality of the selected model input is marked
unavailable because its identity is not recorded. Request byte differences can
include model identity, instructions and provider formatting as well as input
changes. Neither equality nor inequality identifies a cause. Paired results do
not establish a model-only causal effect, and cohort selection does not establish
representativeness. Fixture evidence remains authored software evidence, not
model-quality evidence.

The report also compares definition, adapter, requested model and provider
configuration identities. If either requested model name is redacted, the
model-change flag is unavailable. The CSV repeats these comparison-wide flags
on each case row.

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
case failed strict scoring. V2 CSV adds `explicit_refusal` for each selected
case, including cases with excluded labels. The repeated `refused_count` totals
count only applicable cases and must not be summed across rows. `refusal_reason`
retains the count's scope. V1 CSV keeps its original columns.
To prevent spreadsheet formula execution, cells
starting with formula/control characters are prefixed with an apostrophe; JSON
retains the exact saved display strings. CSV requires a classification preset;
raw material is never included in CSV. Saved-report exports reject `--preset`
and `--pricing`, just like other creation selectors. The Python request accepts
`preset="classification"` and `ClassificationPricing`; the headless API exposes
the same creation fields and CSV download.

Aggregate report content is bounded at 32 MiB and 750,000 JSON value nodes;
saved report envelopes and each exported artifact are bounded at 40 MiB.
Escaping can make the saved envelope reach its bound before the content does.
Oversized reports fail before being saved; exports never truncate case rows,
probability vectors or attempt evidence. Individual user JSON sources retain
their existing 1 MiB admission limit, and ordinary generated JSON retains its
existing 2 MiB limit. Other record envelopes keep their 16 MiB limit.
These are separate from the owned report aggregate.

The offline scale regression exercises 2,500 selected cases and 104 options
through the normal runner with a controlled authored transport, then creates,
replays and exports a saved evaluation through the real CLI. Its full vectors,
attempts, failed/unknown outcomes and excluded expectations remain visible. This
is bounded software verification, not evidence about live model quality or an
unlimited cohort-size guarantee. Other saved-evidence types retain their own
existing bounds.

A paired regression prepares two authored 2,500-case cohorts with 104 options
through the runner's in-memory source port, then persists their frozen records
to a file project. Comparison, replay and exports use the real CLI and file
store. It retains all 5,000 case rows, complete 16-digit probability vectors and
attempts. The expected comparison has 2,496 compatible labelled pairs, one
improvement, one regression and one both-wrong pair. Two unavailable answers,
one disputed expectation and one unlabelled agreement remain outside that
quality denominator. Each side's
full-cohort strict accuracy is 2,494 / 2,498 applicable expectations. Comparison
and report creation make no inference calls.

Older builds retain the earlier report bounds and may reject newly created large
reports. Reverting the code alone is not a complete downgrade path for a project
containing those reports; retain the project and use a compatible reader. No
existing report needs migration to use the new reader.
