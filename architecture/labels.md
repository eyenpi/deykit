# Labels and grouped splits

`LabelService` and `SplitService` depend on `ProjectSource`, `Clock`, and an ID
factory. Pure component construction and assignment live in `domain/splits.py`.
There is no provider, HTTP, filesystem, CLI, or UI dependency in their semantics.
CLI and browser adapters remain separately owned work.

## Label review and explicit mutation

`LabelService.read(decision_id, dataset_id, case_id)` returns immutable `LabelView`
with the full case, current validated draft definition, current label, all exclusion
causes, removed option IDs, and `LabelReview`. Read/list never modify source or
suggest a prediction. `LabelReview` carries decision/dataset/case/question IDs,
the semantic hash of the **full input**, and decision/draft/current-label ETags.
Staged controls retain this review token. `set`, `clear`, `dispute`, `resolve`, and
`batch` require it; each save compares its context under the source lock through
commit. Changed unselected input, options, question, or label causes conflict.
Tag/split edits alone neither stale a label nor invalidate reviewed input.

Current labels use `domain.label_identity.label_id(case_id, question_id)`, scoped
by `(decision_id, dataset_id)`. A second decision cannot read another decision's
labels. Changing display names preserves IDs. Replaced questions and removed
options keep their old IDs visible through list/read and history. The current draft
must validate to determine applicability; an invalid draft reports a safe error
and never silently selects the last saved revision. Historical label inspection
remains available through `history` even when the draft is incomplete.

New set/resolve records require explicit provenance. Existing provenance persists
unless the caller explicitly overrides it; editing imported or model-generated
labels does not implicitly mark them human. Set updates an expectation while
preserving disputed status. Dispute requires an existing label and a nonblank
reason, preserves its original input hash and acceptable set, and records a
`dispute` change. Resolve records the explicitly reviewed acceptable set and
active status. Clear removes current state and appends a `clear` change, including
when already unlabelled. Each non-clear change stores the full immutable label.
History orders by UTC timestamp and stable change ID; tied timestamps do not
assert a separate causal ordering. Dataset/case operation journals also preserve
source history. Labels never increment the dataset revision.

Acceptable sets are nonempty unique stable option IDs; their stored ordering is
canonical. Read returns combined disputed/stale/incompatible causes, preserving
all removed IDs. List supports status filters and stable label-ID cursor pagination.
An old-question incompatible label and the new question's unlabelled view can
both appear for a case. `LabelMutation` returns durable original `LabelChange`
records, so replay does not misreport newer labels as the original result.

Batch validates every target and expected set before writing anything, rejects
repeated targets, and commits current state and append-only history in one source
transaction. Every mutation hashes explicit request intent (including review
tokens), looks up its operation ID **inside** the consistent boundary before
current-state validation or ID/time generation, and replays its original receipt.
A reused operation ID with a different request is a conflict. Rechecking review
tokens also detects external file edits during preparation; arbitrary external
editors must still cooperate with the source lock for atomic writes.

## Grouped split algorithm and persistence

`SplitService.preview` reads the complete current dataset and returns immutable
assignments, connected groups, actual counts, dataset ETag, and source fingerprint.
It performs no writes, clock calls, or ID generation. Full-dataset explicit
assignments are supported; partial/selected-scope assignments are intentionally
unsupported. Every current case must occur exactly once; unknown IDs, invalid
splits, and conflicting destinations inside a group fail visibly.

`connected-greedy-squared-v1` unions explicit group IDs, exact semantic full-input
hashes, and all `derived_from` links. Missing ancestors remain virtual vertices,
so siblings referencing the same removed/missing ancestor stay together. Namespaces
separate case, group, and input-hash vertices. Cycles are supported. Sorted component
members and stable SHA-256 semantic tie keys make results independent of source
ordering and Python hash randomization. Large components are allocated first;
each destination minimizes the exact increase in squared error from desired case
counts. Seeded hash keys break component and destination ties. This is a reproducible
heuristic, not an optimal partition guarantee; indivisible groups can substantially
change actual ratios. Zero-ratio destinations never receive automatic assignments.

Ratios arrive as an exact JSON **source string**, defaulting to development 0.8 /
test 0.2; calibration must be explicit. Only known split names and finite numeric
values in [0,1] are accepted; their exact rational sum must be one. The algorithm
uses `Fraction(Decimal)` so global Decimal precision cannot alter sums or scoring.
Primary references checked 2026-10-05:
[Python fractions](https://docs.python.org/3/library/fractions.html) and
[Decimal contexts](https://docs.python.org/3/library/decimal.html).
Tests ran on Python 3.14.7 with the locked environment; compatibility with other
platforms is not inferred from those documentation checks.

Commit rechecks/recomputes the preview under one source boundary and writes all
case assignments, a new `DatasetRecord.revision_id` via `DatasetService.bump`, and
an immutable `DatasetSnapshot` in one transaction. Snapshot `selection_source`
records algorithm, seed, exact ratios, assignments, groups, actual counts, input
fingerprint, and prior dataset ETag. `deykit-split-snapshot-v1` content identity is
`semantic_hash({"profile": "deykit-split-snapshot-v1", "case_bytes_hashes": [...],
"selection_hash": ...})`, with cases ordered by stable ID and each SHA-256 taken
over `dump_record(case)`; selection uses the shared semantic hash. This projection
supports the 16 MiB aggregate record budget without concatenating all input into
one generated JSON value. Selection remains subject to the 1 MiB source limit.
Oversized evidence fails before commit. Old snapshots, runs, and labels are not
rewritten. A later split or input edit cannot alter the recorded assignments.

## Evidence boundary

Dedicated offline tests cover A12–A15, label staging, provenance, combined causes,
question/option deletion, rename identity, original receipt replay, malformed
requests, batch atomicity/crash recovery, source-lock and review races, removal
and re-addition, exact ratios, virtual ancestors/cycles, ordering reproducibility,
and frozen evidence. These are authored software verification cases, not measured
model quality, live provider, browser, or cross-platform acceptance evidence.
