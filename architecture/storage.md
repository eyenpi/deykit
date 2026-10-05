# Portable project storage (P02)

## Public interface and ownership

`storage.FileProjectSource(root: Path, *, create=False)` is the POSIX filesystem
adapter for `contracts.ports.ProjectSource`. Use it as a context manager or call
`close()`; descriptors have explicit lifetimes. Domain/services depend on the narrow
protocol, never on SQLite or filesystem implementation. `filesystem.SafeFiles`,
`locks.acquire`, the private journal schema, disposable index, and source transaction
orchestrator are separate modules. A Windows adapter can replace filesystem/locking
without changing application contracts; this implementation rejects unsupported
platforms explicitly and makes no Windows compatibility claim.

`application.errors.ServiceFailure` exposes `.error: ServiceError`; its string is the
fixed safe message. Raw filesystem/SQLite/Pydantic exception data is not a service
response. `application.projects.ProjectService(source_factory, clock, id_factory)`
provides `create(path, name, operation_id)`, `open(path)`, `validate(path)`,
`snapshot(path, keys=None)`, and `rebuild_index(path)`. The injected factory accepts
`(Path, create: bool)` and returns a closable ProjectBackend. `ProjectInfo` includes
the strict project record, ETag, actual execution-active probe, count, and optional
index warning. These operations invoke no provider and perform no inference.

Source methods include read/list/consistent-read/commit, `capture_snapshot(keys=None)`,
`operation_history(key)`, `rebuild_index()`, and the execution/cancellation interfaces
below. In a consistent-read context the same instance is reentrant on its owning
thread; competing threads/processes fail with a safe conflict rather than wait while
holding unrelated locks. Application read-modify-write work can use that context, but
must still supply expected ETags for explicit concurrency behavior.

## Authoritative layout

```text
deykit.project.json                  # sole project metadata and ancestor-discovery marker
source/<collection>/<scope...>/<id>.json
history/journal/<operation-id>/       # staged manifests/blobs; recovery required
history/operations/<operation-id>/    # immutable completed manifests and old/new bodies
history/cancellations/<run-id>/       # append-only cancellation requests
history/cancel_ack/<run-id>/          # immutable acknowledgement per resume segment
.deykit/index.sqlite3                 # disposable derived cache
.deykit/locks/{source,execution}.lock  # OS ownership, no PID/timestamp takeover
```

Keep the root marker, `source/`, and **all `history/`** in backups/copies/version
control. Only `.deykit/` is disposable, and removal/copy is supported while the project
is quiescent. Do not delete lock files while processes own the project. An arbitrary
copy during mutation is not claimed transactional. Individual readable JSON files are
used for history rather than sharing a partially writable JSONL tail.

Cases scope by `(dataset_id,)`; labels/label-history by `(decision_id, dataset_id)`;
revisions by `(decision_id,)`; attempts/run-events/segments by `(run_id,)`;
attempt-events by `(attempt_id,)`. Other resources are globally scoped. Draft ID is
the decision ID. IDs in record bodies must match their path and parent scopes.
Case-insensitive aliases in collection, scope and ID path components are rejected,
including retained empty directories, before a transaction is staged; case IDs can
repeat across distinct datasets. Root metadata uses its embedded stable project ID
and is never duplicated under source/. A transaction cannot target the root marker
twice, delete it, or change its established identity. External marker identity changes
conflict with the essential operation ledger.

All reads validate strict typed record envelopes, versions and named hash profiles.
Every completed operation is checked for complete old/new blobs, byte hashes, record
versions and scoped identities; corruption in historical bodies blocks unrelated
reads, mutations and pending recovery writes without repairing the damaged data.
Committed immutable source is checked against essential operation history, including
missing/deleted immutable keys. Revisions, snapshots, runs, attempts/events,
evaluations/comparisons and reports cannot be overwritten or have their IDs reused.
RunSegment permits one terminal `ended_at` transition, preserving every other field;
the end cannot precede the start. Mutable cases/drafts/labels preserve their before
and after bodies in the operation ledger. Explicit regression removal remains allowed.

## Transactions, conflicts and recovery

`commit(operation_id, changes, *, intent_hash=None)` implements an all-or-recover
source transaction. `expected_etag=None` means create-only; otherwise it must match
SHA-256 of current exact bytes. Deletion needs an existing expected ETag. A receipt
contains new StoredRecords plus `deleted_keys`, and a replay flag.

1. Acquire the OS-held source lock; recover any earlier journal before exposing reads.
2. Validate source, identities, versions, immutable evidence, expected hashes and all
   proposed records. Freeze a deterministic change digest and chronological sequence.
3. Durably stage old/new bytes and a versioned manifest using file fsync and directory
   fsync. Recheck source fingerprints against the captured state.
4. Durably persist the commit decision, bound to the manifest hash. Only then replace
   source files atomically one by one, syncing each affected directory.
5. Move the completed journal into essential operation history; sync both parents.
   Only after that update the disposable index.

Before a durable decision, recovery discards staging and leaves old source. After the
decision, recovery finishes the full new state. Every staged body and current target
is validated before recovery writes: targets must match the saved old or new hash.
An unrelated external edit or corrupt blob blocks recovery without overwriting it.
Recovery may be interrupted at every replacement and safely repeated. A caller that
gets an I/O failure after commit decision must reopen/replay the same operation; it
must not assume the operation was rolled back. Index failure after commit reports
`index_unavailable` separately and cannot undo source or consume a second operation.

Default replay checks the complete physical change digest, including expected ETags.
Application-generated IDs/timestamps require the additive intent protocol:
`operation_receipt(operation_id, *, intent_hash)` before generating them, followed by
`commit(..., intent_hash=the_same_hash)`. Canonical application intent includes command,
requested resource IDs/values and expected ETags; exclude only generated IDs/times.
Same committed intent returns the original receipt even after later source edits;
different intent conflicts. Both physical and intent digests remain in the ledger.
The service is responsible for constructing the complete honest intent projection.

`capture_snapshot` validates immutable integrity and compares complete exact source
reads before/after capture, including additions/deletions. Uncooperative external
changes produce `unstable_source`. The source lock coordinates participating clients;
it does not lock unrelated editors or promise a filesystem-wide external snapshot.
Source hash equality is a semantic observation of bytes, not an assertion that an
external file was never transiently touched. Unsupported versions block mutation.

## Execution and cancellation boundary

`execution_owner()` holds a separate nonblocking OS lock for a run. Acquire execution
ownership before the short source lock; attempts to acquire it from a source context
fail `lock_order_violation`. `execution_active()` actually probes that OS lock.
Opening a project reports the observation and does not classify or mutate a run into
interrupted state. Process death releases OS ownership automatically; stale lock files
alone are not ownership. Later runner code remains responsible for reservation,
attempt budgets, explicit resume and unknown-response semantics.

`request_cancel(run_id)` durably appends a cancellation request while another process
may own execution. `cancellation_requested(run_id)` observes unacknowledged requests.
Explicit resume uses `acknowledge_cancel(run_id, segment_id)` only while this source
instance owns execution and the new segment exists. The runner must hold one `consistent_read` source context
across committing that segment and acknowledging prior requests, preventing a newer
cross-process cancellation from being consumed between those steps. The immutable acknowledgement
names prior request IDs; history is retained. A later cancellation cannot be consumed
by repeating the same segment acknowledgement. Crashing before acknowledgement leaves
the run cancelled, and opening never acknowledges or resumes it automatically.
Project validation also checks every cancellation and acknowledgement version, file
identity, run reference, segment reference and acknowledged request reference. An
unrelated operation cannot bypass damaged cancellation history.

## Cache and filesystem guarantees

SQLite is built from authoritative records in an in-memory connection, serialized,
then atomically replaced through the safe filesystem adapter. It holds only scoped
IDs and ETags. Deleting/corrupting it changes no source or history; rebuild is explicit.
No source operation reads SQLite to decide truth or replay an operation.

Internal filesystem traversal uses anchored directory descriptors and O_NOFOLLOW;
symlinked internal directories/files, nonregular source files, and multiply linked
source files are rejected. Reads open nonblocking and check the opened descriptor
before consuming bytes, so a FIFO cannot hang validation while holding the source
lock. Files use owner-only creation permissions. This blocks
path escape through supplied IDs and static/internal symlinks. The project directory
is an explicit trusted user selection; same-user hostile mutation of every internal
file is not a security isolation boundary. Physical power-loss guarantees ultimately
depend on the OS/filesystem honoring fsync. Tests establish software crash behavior,
not disk-controller power-loss behavior or network-filesystem lock support.

## Evidence and primary references

P02 tests use no keys/inference and cover A05–A08, subprocess hard exit at each journal
boundary and during recovery, stale-write conflicts, changed operation payloads,
intent replay, deletion history, deleted immutable identity reuse, index failure,
copy/rebuild, actual OS ownership/process death, lock ordering, durable cancellation,
external edits, symlink/hardlink boundaries, child-process FIFO rejection, retained
empty-directory aliases, stable root identity, historical blob corruption and global
cancellation-history validation.

Research checked 2026-10-05: [Python flock](https://docs.python.org/3/library/fcntl.html),
[Python fsync and directory-relative filesystem operations](https://docs.python.org/3/library/os.html),
and [SQLite atomic commit assumptions](https://www.sqlite.org/atomiccommit.html).
Tests run with the locked Python dependency set, CPython 3.11.16 with SQLite 3.53.1 on macOS ARM64;
CI checks Ubuntu Python 3.11/3.13. Actual CI status must be read from the PR.
