# Classification experiments

An experiment expands frozen decision revisions, dataset cohorts and provider
profiles into runs. Its attempt and estimated spending limits apply across all
members, including retries and diagnostic requests. Jev and OpenAI choice
profiles are supported. Fixture mode is available for offline software checks.

Save a configuration outside the repository. This example selects one dataset
and compares two configured live provider profiles:

```json
{
  "mode": "live",
  "decisions": [
    {"decision_id": "route", "revision_id": "revision-1", "modality": "text"}
  ],
  "cohorts": [{"dataset_id": "products", "split": "test", "case_ids": []}],
  "variants": [
    {"name": "jev-model", "provider_id": "jev-profile", "reservation_usd": "0.005"},
    {"name": "openai-model", "provider_id": "openai-profile", "reservation_usd": "0.010"}
  ],
  "settings": {
    "max_attempts": 5000,
    "concurrency": 16,
    "timeout_seconds": 60,
    "deadline_seconds": 3600,
    "max_retries_per_case": 0
  },
  "budget_usd": "30.00"
}
```

By default, the decision, cohort and variant lists form a Cartesian product.
To run only selected combinations, add an `include` list with zero-based
decision and cohort indexes and the variant name. Every declared decision must
appear at least once. For example:

```json
"include": [
  {"decision_index": 0, "cohort_index": 0, "variant": "jev-model"},
  {"decision_index": 1, "cohort_index": 0, "variant": "openai-model"}
]
```

A diagnostic must refer to a selected main combination. A decision must name a
saved revision. Set `modality` to `image` when that revision selects
managed images, or `text` when it selects none. The provider profile supplies
the model and credential reference. The configuration contains no secret values.
For fixture mode, use `"mode": "fixture"` and replace each `provider_id` with
`fixture_set_id`.

`reservation_usd` is the caller's estimated dollar reservation for one attempt.
It is not a token price, a billed amount, or a promise that the provider cannot
charge more. Supply a conservative estimate that accounts for input, output,
images and any provider-specific charges. Amounts are decimal strings with at
most nine fractional digits. The reservation for every attempt stays charged
against the experiment limit, including an unknown outcome or an attempt that
was not sent. This conservative rule makes interruption and retries safe but
can leave less usable capacity than the final bill would imply.

Set `reservation_usd` to `null` when the price is unknown. The preview shows the
unknown count. A run with a dollar budget rejects an unknown reservation before
dispatch. If `budget_usd` is `null`, the attempt limit still applies and the
report identifies attempts without a price. Reported usage may also be unknown.
Neither reservations nor usage establish billed cost.

Review the entire preview and keep it for the start operation:

```sh
deykit --project /absolute/project --json experiments preview /absolute/experiment.json \
  > /absolute/experiment-preview.json
deykit --project /absolute/project --json experiments run /absolute/experiment.json \
  --preview /absolute/experiment-preview.json --operation-id experiment-start-1
```

The preview lists each member's case IDs, compiled request identities, input
failures, request count and price assumption. The start checks its reviewed
context hash against the current sources before freezing and dispatching. Keep
the same configuration, preview and operation ID for a retry after an uncertain
result. A replay does not dispatch again. A new intent needs a new operation ID.

Reports disclose the requested model and counts of reported model identities
among valid answers, including how many valid answers lack a reported identity.

`settings.concurrency` limits the total number of simultaneous requests across
the experiment. The scheduler may run variants in parallel. The attempt cap
can be smaller than the expanded request count. When the remaining attempt or
spending reservation cannot cover a request, that request remains pending.
The experiment allows at most 100 expanded members, including diagnostics,
and at most 512 MiB of planned and frozen records across all
members. A JSON preview is limited to 64 MiB so the saved review can be read
back by the run command. The stored experiment selection is limited to 4 MiB;
individual frozen records, including each dataset snapshot, retain the normal
16 MiB record limit. An oversized preview fails without starting work. The
expanded explicit case selections are limited to one million case references
across all members, including diagnostics; this bound is checked before plans
are built. Omitting a cohort's case IDs selects the dataset without expanding
those IDs in the configuration. The 512 MiB plan bound includes each compiled
image request, so the number, size,
and reuse of images affect the largest supported experiment.
When a missing revision or an oversized selection prevents an exact diagnostic
count, an incompatible preview reports `unplanned_members` as `null`.
Each member's result snapshot also has the 16 MiB record limit. For live arms,
preview rejects a selection when even a minimal full probability distribution
cannot fit after reserving space for all selected cases and the maximum number
of answers permitted by the lifetime attempt cap and valid inputs. An unexpectedly larger
answer is recorded as `response_error` with reason
`experiment_result_resource_limit`; available raw response and usage evidence
remain attached to the attempt. This keeps the snapshot and recovery writable.

The run command prints its group ID to stderr after the group is saved and
before provider requests start. Inspect, stop and recover it with that ID:

```sh
deykit --project /absolute/project --json experiments show GROUP_ID
deykit --project /absolute/project --json experiments cancel GROUP_ID --operation-id cancel-1
deykit --project /absolute/project --json experiments resume GROUP_ID --dry-run
deykit --project /absolute/project --json experiments resume GROUP_ID --operation-id resume-1
```

Resume does not reset either limit. Unknown outcomes are not retried unless the
user explicitly supplies `--retry-unknown`; another attempt consumes another
reservation and may duplicate a remote call. The resume preview lists eligible
cases and an upper bound on dispatchable attempts for each member. These bounds
are not additive: members compete for the same remaining attempts and dollars.
A provider-wide failure stops requests using the same frozen provider profile;
other profiles may continue or resume within the original shared limits.
Inspection does not start work.
The JSON progress includes member runs, case states, attempt counts, known
reserved dollars, remaining dollars, unknown prices and unknown usage.

Use the `group.snapshot_id` from progress to pin a report. The report summarizes
all members in one JSON envelope, without raw inputs, requests or responses:

```sh
deykit --project /absolute/project --json experiments report GROUP_ID \
  --snapshot SNAPSHOT_ID > /absolute/experiment-report.json
```

The report includes selected cases, status and exclusion counts, applicable
expectations, full-cohort strict accuracy, valid-answer accuracy, usage and
latency. Full-cohort accuracy includes pending, invalid and unknown answers in
the applicable expectation denominator. Exclusion counts may overlap. For a
saved, detailed classification report or CSV for one member, use its `run_id`
and `result_snapshot_id` with `report export --preset classification`.
Fixture results are authored software evidence, not observed model quality.

Projects containing experiment records need a Deykit version that understands
them. Older versions reject the new group and snapshot types. Keep a project
copy or a compatible Deykit version available before rolling back the software.

## Fresh diagnostics

Add `diagnostics` to the configuration to select cases for fresh repeat or
option-order requests. Indexes refer to the zero-based decision and cohort
positions, and `variant` names one configured variant. Each case must belong to
the selected cohort. These requests use the same lifetime budgets as the main
members and are marked `repeat` or `choice_order` in the output.

```json
"diagnostics": [
  {"kind": "repeat", "name": "repeat-check", "decision_index": 0,
   "cohort_index": 0, "variant": "jev-model", "case_ids": ["product-1"], "count": 2},
  {"kind": "choice_order", "name": "order-check", "decision_index": 0,
   "cohort_index": 0, "variant": "jev-model", "case_ids": ["product-1"],
   "orders": 4, "seed": 42}
]
```

Choice-order diagnostics include the original order and up to three distinct
seeded alternatives. Repeat and order diagnostics are fresh requests, even when
their request bytes match a main member. The experiment report includes a
disagreement rate for each diagnostic. For repeats, it compares fresh answers
with the main answer; for option order, it compares answers across orders. The
report gives the number of comparable and excluded cases as well as the number
with all requested answers present.

## Reuse a completed experiment

Set `reuse_group_id` to an existing completed, main-only experiment group to
request reuse of the entire group. Preview checks every member's frozen
definition, case and image identities, provider configuration, compiled
request, labels and valid result. A mismatch rejects reuse. The reuse receipt
pins the original group snapshot and records zero fresh attempts and zero new
reservations. Its `reuse_id` can be passed to `experiments show` and
`experiments report`. A configuration that requests reuse cannot also request
fresh diagnostics; run those in a separate experiment. Partial member or
individual case reuse is not supported.
