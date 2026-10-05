# Portable project storage (P02)

## Public interface and ownership

`storage.FileProjectSource(root: Path, *, create=False)` is the platform filesystem
adapter for `contracts.ports.ProjectSource`. Use it as a context manager or call
`close()`; descriptors have explicit lifetimes. Domain/services depend on the narrow
protocol, never on SQLite or filesystem implementation. `filesystem.SafeFiles`,
`locks.acquire`, the private journal schema, disposable index, and source transaction
orchestrator are separate modules. Private POSIX and Windows backends sit beneath SafeFiles without changing application
contracts. Windows uses native handles; POSIX retains directory descriptors. Closing
the facade rejects every later operation before an OS identifier can be recycled.

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
3. Stage old/new bytes and a versioned manifest with checked file flushes (and
   parent-directory fsync on POSIX). Recheck source fingerprints against the captured state.
4. Persist and flush the commit decision, bound to the manifest hash. Only then replace
   source files atomically one by one; POSIX also syncs each affected directory.
5. Move the completed journal into essential operation history; POSIX syncs both parents.
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

POSIX traversal uses anchored directory descriptors and O_NOFOLLOW;
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

## Windows adapter and evidence boundary (P18 storage subtask)

`_filesystem_windows.py` owns traversal and resource lifetime; `_win32.py` alone owns
ctypes bindings. Internal components are opened with `NtCreateFile` relative to a
retained directory HANDLE, `OBJ_DONT_REPARSE` and `FILE_OPEN_REPARSE_POINT`. The opened
object must be a disk object, have the required type, have no reparse attribute, and
have one hard link if it is a file. Reads enforce size limits before and during I/O.
Enumeration uses `GetFileInformationByHandleEx`; normalized long-name queries verify
opened names as well as the shared casefold policy (including custom 8.3 aliases).
No checked absolute path is subsequently reopened for internal operations.

Parent guards omit delete sharing and remain alive throughout traversal and lock
ownership. Readers allow read/write/delete sharing; lock handles allow read/write
sharing only. Fresh same-directory temporaries are exclusive, binary, flushed with
`FlushFileBuffers`, and renamed by handle with a destination directory handle.
Archival renames prohibit replacement. Deletion is through a validated handle.
Handles are non-inheritable, never converted to CRT descriptors, and closed exactly
once, including validation failures. Windows inherits the selected directory's ACL;
POSIX creation uses owner-only mode bits. Choose a private project directory.

`LockFileEx` locks byte zero exclusively with FAIL_IMMEDIATELY. Only
ERROR_LOCK_VIOLATION means contention; permission/invalid-handle/I/O failures remain
errors. Unlock/close occurs on every normal exception path. Process termination
releases ownership, with bounded polling in acceptance tests where Windows may delay
release. Lock ordering and source/execution independence are unchanged.

The intended Windows evidence is **process-crash recovery on tested local NTFS**.
There is no assumed Windows equivalent to parent-directory fsync. Physical
power-loss and OS-crash ordering remain **unverified on every platform**. Network,
cloud-synchronized and other filesystems are outside the tested guarantee. The
trusted project selection is not a security sandbox against arbitrary hostile
same-user mutation. Full P18 packaging, bundled browser assets, physical keyboard/UI
acceptance, and authorized provider evidence remain separate integration gates.

`portability.yml` runs the full offline suite on `ubuntu-24.04`, `macos-15` and
`windows-2025`, Python 3.11/3.13. It records OS/build, Python patch, architecture,
filesystem, SQLite, commit and lockfile identity, and archives JUnit skip/results.
Windows hosted Server CI does not demonstrate a physical Windows 11 desktop. Read
actual PR checks for results; a workflow definition is not platform evidence.

The dedicated cases cover closed-object/recycled descriptor sentinels, Unicode/long
roots, exact binary bytes, device/ADS/traversal aliases, empty-scope collisions,
hardlinks in each file role, junctions/reparse roots, Windows sharing, failure
cleanup, separate process contention and kill release, and child inheritance.
Existing journal tests interrupt commits and recovery. Runner process tests use
parent-issued `Popen.kill()` after observed checkpoints on both platforms, preserving
in-flight unknown-outcome, cancellation and explicit-resume assertions. Synthetic
native failure injection is unit software evidence, not Windows platform evidence.

Primary references checked 2026-10-05:
[NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[handle enumeration](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex),
[handle rename](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info),
[LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex),
[FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers),
[short-name aliases](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setfileshortnamew).
