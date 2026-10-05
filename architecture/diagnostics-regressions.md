# Diagnostics and frozen regression checks

P12 composes the existing planner, reservation repository and scheduler. Each option
order is a distinct logical run. The original order precedes at most three distinct
seeded alternatives (`deykit-choice-order-v1`); two options yield at most two orders.
The summary keeps the independent case denominator separate from expanded results.
Only cases with at least two valid semantic answers enter disagreement measurement.
Missing outcomes remain unavailable; authored fixtures establish software behavior.

An immutable `ExecutionGroup` binds exact member manifest hashes, original selection,
a fixed lifetime attempt cap and a segment deadline duration. All members are prepared
from one source epoch and frozen in one transaction. Preview accounts for the same
32 MiB serialized evidence boundary, including initial segments and readiness markers.
Each reservation counts against both its child limit and the fixed group cap. Retries,
unknown outcomes and not-sent reservations consume capacity permanently. Direct child
resume or cap extension is rejected with the actionable group identity.

One OS execution owner covers a whole group segment. One monotonic scheduling deadline
is passed unchanged to every child scheduler. In-flight work settles within its attempt
timeout; the scheduling deadline stops new requests. Explicit group resume creates a
new time window with the original duration while retaining all consumed reservations.
Unknowns are skipped unless explicitly retried. Definitive provider-wide failures require
a new scope rather than automatic group resume.

Cancellation remains `runs cancel MEMBER_RUN_ID`. The repository observes controls above
each member's frozen segment cutoff under the source transaction, stopping fresh group
scheduling. Old acknowledged controls do not cancel a later segment. Legacy flag
acknowledgement and durable readiness markers remain inside the segment source boundary.
No await occurs under source ownership. Replay never dispatches or acknowledges new
cancellation; retained receipts are rendered after leaving the source lock.

Captured admission verifies group/member hashes, segment ownership and time windows,
all retained group snapshots and their exact result/event boundaries before recovery.
A missing final summary is repaired only under actual execution ownership, after another
captured admission, with no new child segment or request. The group/segment/ordered result
references deduplicate repair. Corrupt retained evidence produces no repair mutation.

Regression authoring makes zero calls and freezes the full original CaseRecord, exact
input hash, explicit acceptable IDs, reason, provenance and immutable origin references.
Origin admission compares frozen run/revision/result/case/attempt evidence; self-hashing
alone is insufficient. Removal appends an immutable control and leaves old membership
readable. Incomplete legacy records stay metadata-visible and nonexecutable. Checks never
upgrade them from current cases. Compatible identical frozen cases share one request and
retain separate oracles; conflicting versions within a dataset are rejected.

Checks compile the current draft by default, or an explicitly selected revision, against
frozen inputs and stable question/option/schema compatibility. Mutable inputs, current
labels and predictions do not become expectations. Visibility and default membership
are rechecked before freeze. Empty fitting snapshots carry the explicit reason
`frozen_regression_selection`: baseline accuracy is null, fitting/scoring support zero.
Regular run baseline behavior retains its full frozen development source.

Public pure readers are `application.diagnostics.diagnostic_snapshot_from_records` and
`application.checks.check_snapshot_from_records`. They require an exact snapshot ID and
return frozen typed evidence with ordered members. They access no source, provider,
clock or lock and perform no recovery or metric persistence. P13/P14 consumers can pin
these boundaries; interactive progress is a separate current view. Default CLI views
show hashes/compiler/model/order identities, semantic outcomes and safe provenance,
with no raw input/request/response bodies.

Tests use fake ports/clocks, real authored FixtureSets, source faults, concurrent source
boundaries and parent-issued subprocess kills. Parent kill follows Python's
[subprocess documentation](https://docs.python.org/3/library/subprocess.html#subprocess.Popen.kill).
This is software process-death evidence; actual Windows execution depends on integrated
portable storage and CI. No live-provider quality or physical power-loss claim follows.
