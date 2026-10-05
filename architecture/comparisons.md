# Immutable comparison boundary

`comparisons.models` defines strict versioned evidence values, and
`comparisons.pairing` assigns one disjoint bucket per union case. Neither depends
on HTTP, SQLite, SDKs, CLI or UI. `ComparisonService` depends on the source and
clock ports and consumes the shared captured-evaluation admission helpers plus
pure `assess_results`; it does not implement correctness again.

The existing immutable `ComparisonRecord` holds requested evaluation/result
references and a versioned typed `outcomes_source`. That source retains both
run, decision, dataset, revision, dataset/label/result/evaluation snapshot IDs
and hashes, provider/model/compiler/order context, side-specific assessments and
complete accounting. The record's semantic hash includes the typed source and
references using the shared exact JSON hash profile. Shared contracts and the
storage registry need no changes.

Compiler IDs come from immutable prepared cases, summarized in deterministic
order; each side retains its exact request body hash when preparation succeeded.
The service reads that metadata from one captured source snapshot and checks
run/case scope, input hashes, adapter, version and requested model. Saved reads
also bind every side assessment to the original immutable revision, labels and
results using the shared pure assessment logic. Acceptable-set and legacy-label
rules remain shared. Saved outcomes are returned intact after validation.

Creation checks its durable operation receipt under source ownership before
generating IDs or timestamps. The intent names the ordered immutable evaluation
IDs. Frozen context validation and one atomic comparison write occur within that
source boundary. Read/replay checks strict source version, hash, count
conservation and context/reference links against immutable evaluation evidence.
It never recomputes a saved outcome using mutable labels or current results.
Creation and decoding share one pure classifier, so coherent counters cannot
hide a bucket inconsistent with its side assessments. Creation uses one captured
batch plus a deliberate second capture before commit for drift detection;
read/replay uses one batch, with no cache beyond the source boundary.

The CLI resolves explicit pins, or original evaluations of the current result,
under one source boundary and exposes actual selections. If no original
evaluation exists, the shared evaluation service creates it with a stable
result-specific operation ID. `reevaluate` stays owned by P10. CLI comparison
does not compile requests, resolve credentials or dispatch transports.

Offline verification uses independent pure accounting oracles and genuine
P08-runner-produced authored fixture snapshots, including dispatch and settlement
records. A quiescent closed project seed is copied into isolated test projects;
the copies share no execution ownership or mutable source. These tests verify
software behavior, not live provider quality or manual platform acceptance.
