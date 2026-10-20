# Bulk execution and control responsiveness

Issue #57 concerns local overhead and unavailable controls during ordinary runs. The
benchmark uses generated two-option text choices and a controlled fake transport. It
makes no provider request and establishes no model quality or 104-option Beauty
benchmark equivalence.

## Changes and invariants

A source lock acquisition admits one validated epoch. Nested reads reuse its exact
records; successful local commits replace that view with their validated changes.
Re-entering the source lock reads source and operation history again. Pending recovery
and the commit decision boundary invalidate the view, including a visible archival
rename followed by an I/O error. Snapshots still compare independently read source
bytes, and a commit compares source again before its durable decision. No timestamp,
SQLite entry, or cached filesystem metadata substitutes for those byte reads.

Completed operation validation can reuse successful results only when the operation's
entire freshly read file inventory and bytes match. Historical additions, removals,
changed bytes and duplicate sequences still fail admission. Its memo retains at most
65536 operations / 128 MiB of raw and decoded evidence bytes. Body and lifecycle decoding memos each retain
at most 131072 entries / 64 MiB of serialized bytes. These are retention bounds, not
process RSS limits. There is no persistent validation cache. New operations can use
the compact layout below; existing source/history is not automatically migrated.

Run history indexes records by collection/scope and attempts by case/identity. A
frozen history reuses its result projection; a new captured history gets a new view.
Decoding reuse is keyed by the record type, scoped identity, exact bytes and ETag.

For at least 64 selected cases, the normal scheduler publishes preparation and
settlement batches bounded by the configured concurrency (maximum 64). Reservation
and dispatch events precede every transport call. Failure to publish a received batch
stops execution; an uncertain commit is inspected by normal recovery rather than
replayed as fresh inference. Small runs and explicitly instrumented transition hooks
retain individual transition scheduling. Both paths use the same reservation,
eligibility and settlement rules.

Bulk source work runs on a worker thread. While transport calls occupy all slots, the
scheduler waits for completion rather than repeatedly rebuilding unchanged history.
A due retry with spare capacity can also wake it. Cancellation is checked before any
new preparation; in-flight calls still drain under their request timeouts. Cancellation joins any pending source
publication and drains transport tasks before releasing execution ownership. A
cancel observation prevents further preparation. Received in-flight outcomes settle;
proven non-calls remain pending and interrupted/unknown attempts require explicit
resume policies. Frozen requests and lifetime caps are unchanged.

Review digests use the existing 32 MiB plan budget with a two-million-node bound.
Scoped record fingerprints and group evidence digests use the existing 16 MiB /
one-million-node record budget. Group evidence reconstruction admits that same node
budget before enforcing its typed semantic constraints. These explicit internal
metadata limits allow 10000 selected cases without changing canonical bytes, hash
profiles, ordinary model admission, or user input and provider wire limits. Review
budget exhaustion returns a safe preflight error before execution writes.

Active CLI progress reads use the existing five-second source acquisition budget.
Only acquisition conflicts are retried. Cancellation's durable operation and progress
projection execute once after entry; provider calls are never acquisition retries.

## Reproduce

Run expensive commands sequentially. Each invocation requires a new absolute output
directory outside the checkout:

```sh
uv run python tests/runner/benchmark_bulk.py --count 100 --concurrency 64 --output /absolute/new/bulk-100
uv run python tests/runner/benchmark_bulk.py --count 1000 --concurrency 64 --output /absolute/new/bulk-1000
uv run python tests/runner/benchmark_bulk.py --count 2500 --concurrency 64 --controls --controls-after 2048 --output /absolute/new/bulk-2500
```

The script imports all cases through `ImportService`, previews the complete run and
executes the standard `ExecutionService` over the real filesystem adapter. It asserts
that every selected case has one unique transport call and a saved valid result.
Import, preview, execution and final read timings are separate. Reported transport
latency is zero; execution wall time includes scheduling, validation and durable I/O.
`--controls` holds concurrent calls, invokes actual `runs show` and `runs
cancel` commands in separate processes, drains those calls and explicitly resumes
pending cases in the same project. Its wall time includes that deliberate control
exercise. Both command durations must be below five seconds, including interpreter
startup. It is not a paid/live benchmark.
`--controls-after 2048` lets 2048 calls settle before holding the next concurrent
batch, exercising controls against substantial existing history. Start small and
increase only after the smaller checks pass; no full execution is needed to profile
the filesystem operation counts.

`--profile` aggregates source epochs from their actual threads, including recovery,
reservation, dispatch and settlement storage work. Profiled timings must not be mixed
with ordinary timings. New projects prevent run/operation reuse; source validation
memos and the OS file cache are naturally warmed by import/preview. The script does
not flush OS caches. Fresh processes, selected/planned/call counts, persisted results
and unique call IDs rule out reused results or skipped requests as speedups.

## Regression checks and limits

- Nested reads perform one source traversal and one recovery admission per entered
  epoch. A failed/partially visible commit invalidates that view before another read.
- A 64-case run at concurrency 16 uses at most 12 source commits, including preparation,
  settlement and lifecycle boundaries. Every call observes its durable dispatched
  request through an independent source adapter.
- Real CLI progress and cancellation complete in under five seconds with eight calls
  in flight. All eight outcomes settle; the other 56 cases remain pending.
- Cancellation/resume, actual process death during a bulk transport, an error after a
  durable settlement, operation replay and exhausted lifetime capacity do not repeat
  completed calls. Unknown retries require explicit authorization.
- Existing storage corruption, exact-byte, snapshot race and crash recovery checks
  remain required. No acceptance threshold is implemented by skipping these checks.

The authoritative file layout still requires reading growing source/history at each
new lock acquisition. These changes reduce repeated work and transaction counts;
they do not claim asymptotically linear filesystem execution, bound provider latency,
or qualify Windows without native Windows verification. Use a suitable explicitly
chosen concurrency within the provider's authorized limits; defaults are unchanged.

## Local measurements

An initial 10-case diagnostic profile spent 4.44 seconds of a 7.00-second execution
inside 250 full operation-integrity checks, with 39 history reconstructions taking
2.46 seconds. These cumulative times overlap. Source capture, integrity checks and
history rebuilding were repeated for individual reservation, dispatch and settlement
transitions. A later 100-case worker-thread profile still spent 2.77 cumulative seconds
in filesystem tree reads out of 5.05 profiled seconds: fresh global validation remains
the dominant scaling cost. Profiled runs are diagnostic and excluded from the timing
comparison below.

Unprofiled local measurements use Python 3.14.7 on macOS arm64, concurrency 64 and two
options. The 100-case comparison starts from base commit `31ea9366028a` and uses byte
identical imported input, settings, selected IDs and every compiled request. Every
completed row has exactly N planned cases, unique calls, saved attempts and valid
saved results. An initial 10000-case probe failed its generic 2 MiB hash bound before
any execution; that failed run is excluded.

| Cases | Revision | Import (s) | Preview (s) | Execution (s) | Final read (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 100 | Base | 0.180 | 0.115 | 463.712 | 2.347 |
| 100 | Fix | 0.144 | 0.075 | 2.022 | 0.120 |
| 1000 | Fix | 2.265 | 0.708 | 59.239 | 1.226 |
| 2500 | Fix, cancel/resume | 10.072 | 1.765 | 347.171 | 3.429 |
| 10000 | Fix, loaded host | 132.498 | 7.854 | 7029.353 | 25.723 |

The matched 100-case execution is approximately 229 times faster locally. The
2500-case project used no shards; its real CLI progress read took 1.947 seconds and
cancellation took 2.380 seconds, including interpreter startup. It explicitly resumed
pending cases and completed with 2500 unique calls and results. These execution
measurements preceded the explicit internal metadata hash-budget repair; that repair
preserves the digest bytes used by these smaller runs. The control measurements hold
the first 64 calls in flight; they do not measure controls against the final history
or at 10000 cases.

The final 10000-case run completed on the repaired tree with all 10000 unique calls,
attempts and valid saved results. Its 117.2-minute execution still demonstrates
substantial local overhead. A separate test investigation shared the host at startup;
later observations showed heavy app-renderer and system-service CPU activity. This
row is completion evidence on a loaded host, not a controlled scaling ratio against
the smaller runs. Only 100 cases have a matched before/after timing; no larger-base
timing or speedup is claimed. The remaining full source/history reads are a material
limit, and no wall-time threshold for 10000 cases is claimed.

Final offline verification after the internal hash-budget repair: 1328 tests passed,
21 skipped; Ruff, formatting, mypy, source/wheel builds and clean wheel/sdist CLI
installation checks passed on this macOS host. No live provider or native Windows
verification was performed.

## Follow-up: bounded I/O profiling

The next iteration uses 100 cases, then 300, then 1000. It does not rerun the full
suite or the 10000-case execution. Two avoidable costs were reproduced before fixing:
16 updates enumerated one sibling directory 68 times, and two operational history
reads in an admitted epoch performed three full source walks instead of one.

`SafeFiles.read_many` now selects exact paths through one anchored walk of their
shared parents. Staging and application use ordered batch writes on POSIX, retaining
only the current directory ancestry. Directory spelling is checked on entry and exit;
each replacement still checks the target type/link count and retains file/directory
flushes. Existing `staged:N` and `applied:N` fault checkpoints remain in order. Handles
and spelling inventories are discarded at the end of each batch. Windows retains
individual writes plus final spelling checks; no Windows speedup is claimed.

Operational repository reads can use the optional `RecordViewSource` capability.
Each new lock acquisition still reads and validates source/history bytes; nested
observations reuse that admitted view, just as individual source reads do. Independent
snapshot comparisons for previews/freezing and the fresh source comparison before a
commit decision remain in place. Adapters exposing only `SnapshotSource` retain their
existing snapshot-based history path. Stored layout, request bytes and hash profiles
are unchanged.

| Cases | Mode | Before execution (s) | After execution (s) |
| ---: | --- | ---: | ---: |
| 100 | Profiled | 3.571 | 2.207 |
| 300 | Profiled | 15.184 | 8.173 |
| 1000 | Unprofiled, earlier baseline | 59.239 | 31.285 |

Every row completed with exactly N planned cases, unique transport calls, attempts
and valid saved results. Imported bytes, input hashes and every compiled request were
independently compared and match. Both 100/300 pairs were measured in this iteration;
the 1000 baseline is the earlier measurement above, not a new matched host timing.
Profiled timings are not compared with unprofiled timings.

At 300 cases, path-spelling checks fell from 66472 to 1029, directory listings from
93884 to 14134, and full source walks from 61 to 36. A separate read of the completed
1000-case project captured 9018 records: 5.130 seconds cold and 0.824 seconds warm,
with profiling enabled. Even the warm read opened 19185 filesystem objects. Fresh
whole-project traversal remained the scaling floor; these reductions did not establish
that the 10000-case runtime was acceptable. The user subsequently approved compact
storage for new immutable lifecycle evidence, implemented below.

Focused storage/recovery checks passed (40 tests in 6.9 seconds); batch traversal,
corruption, group snapshot and bulk runner checks passed (88 tests, 3 skipped, in
29.4 seconds); body validation, paths, replacements and API route checks passed
(32 tests, 2 skipped, in 0.7 seconds). Ruff, formatting, mypy and package builds passed.
The earlier full-suite result applies to the preceding commit, not this follow-up.

## Compact evidence follow-up

New attempts, attempt-events, run-events and prepared-cases are stored as exact bytes
inside bounded, immutable per-operation packs, rather than one source file and one
history file per record. Large operations also pack their historical old/new bodies;
mutable source JSON remains individual and editable. Independent source references
guard against losing an entire archived operation. The current adapter reads legacy
and packed histories together; older adapters reject the new format. See the
[storage contract](storage.md) for framing, limits and recovery semantics.

Each new admission still reads authoritative source and history bytes. Exact-byte
validation memoization, snapshot comparisons and the independent predecision read
remain in place. Binary framing does not change record bytes, resource identities,
ETags, request input, or hash profiles. Copies remain self-contained after deleting
the disposable index. Decided transactions recover after process death before
application, during application, or after publishing the reference.

The remaining 300-case profile exposed a Python character loop validating Unicode
scalars. Strict UTF-8 encoding now performs the same validation in C and supplies the
encoded bytes for the existing size check. Lone surrogate keys/values still fail;
Unicode scalar values and exact decimal/integer behavior remain unchanged.

Measurements and focused verification for code commit `edaeb08` are recorded below.
After the small checks passed, the user authorized 5000 cases and then 10000 if the
first run passed with reasonable timing. Both fresh projects passed; no full test
suite was repeated.

| Cases | Mode | Import (s) | Preview (s) | Execution (s) | Final read (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 300 | Profiled | 0.167 | 0.171 | 2.921 | 0.066 |
| 1000 | Unprofiled | 0.515 | 0.565 | 7.226 | 0.103 |
| 2500 | Unprofiled, late cancel/resume | 1.255 | 1.366 | 44.797 | 0.264 |
| 5000 | Unprofiled | 2.444 | 2.556 | 119.978 | 0.477 |
| 10000 | Unprofiled | 5.382 | 5.471 | 482.234 | 1.205 |

All rows have exactly N planned cases, unique calls, saved attempts and valid saved
results. Imported bytes, every input hash and every compiled request were independently
compared with the preceding 300/1000-case receipts and match. The 2500-case control
check waited for 2048 settled calls, held 64 calls in
flight, then cancelled, drained and explicitly resumed. Real CLI show took 2.569
seconds and cancel took 2.769 seconds, including startup. These differ from the
earlier first-batch control experiment and are not a matched speedup comparison.

For the 300-case profiles, filesystem opens fell from 205022 before this follow-up
to 15006 with compact storage (92.7% fewer); directory listings fell from 93884 to
3571. The earlier unprofiled 1000-case execution was 59.239 seconds versus 7.226 now,
but those timings were collected at different times on the same host. The new
10000-case run completed in 8.04 minutes, compared with the earlier 117.2-minute
loaded-host run; these are not matched host conditions, so no controlled speedup
ratio is claimed. Doubling from 5000 to 10000 took approximately four times as long,
so above-linear local overhead remains. These larger runs exercise ordinary execution;
they do not extend the 2500-case CLI control measurements. Large existing
legacy projects still incur their original per-record file reads; this change speeds
newly written evidence without migrating old data.

Final focused verification: 154 tests passed across exact JSON, source/journal
validation, recovery, demo receipt admission, debugging projections, compact packs,
source epochs, bulk execution and group snapshots. The two bounded groups took 5.5
and 15.6 seconds. Coverage includes malformed framing, same-size/mtime corruption,
missing archives/references, mixed legacy evidence, copied projects without caches,
actual child-process death, uncertain settlement, deadline and cancellation/resume.
Ruff, formatting, mypy (191 source files), and source/wheel builds passed.
The legacy full-suite result above applies only to the earlier implementation.
