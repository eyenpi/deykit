# Bounded execution and immutable evidence

The runner depends on `SnapshotSource`, `ExecutionProject`, `BackendFactory`, `Clock`,
and `Waiter`. The application service coordinates the project execution owner;
`Planner` validates and captures source, `RunRepository` appends atomic lifecycle
records, `Scheduler` dispatches bounded asynchronous work, and `views` exposes safe
command/API data. `ProviderBackends` is the composition adapter for Jev and authored
fixtures. No domain contract imports HTTP, the CLI, SQLite, or a provider SDK.

## Capture and preparation

`ExecutionService.preview` performs local validation and compilation without run
records or inference. Start checks the semantic operation receipt under the source
boundary before reading mutable authoring state or generating IDs. A repeated start
returns the original run without dispatch, even after later edits or interruption.

The current validated draft is the default; an explicit revision selects saved
content. Start captures a definition revision, selected cases and labels, and a
separate **full development** dataset/label snapshot. Labels never enter compiled
input. Each selected case has an immutable `PreparedCase`: exact compiler/version,
provider destination/model, bytes and byte hash, or a safe zero-request input error.
The final capture fingerprint is checked before the atomic freeze transaction.

An optional stable-ID `option_order` must be an exact permutation. It changes only
the validated in-memory compilation copy, retains the original frozen definition for
evaluation, and is recorded in the manifest and semantic caller intent. Resume keeps
the saved bytes; an unmatched authored permutation never falls back to live.

The manifest freezes the non-secret provider profile and optional fixture-set ID.
Resume reads those records and saved request bytes, never current drafts, case
inputs, provider configuration, or a newer compiler. Secret values are resolved
only through the frozen reference at explicit execution preflight/dispatch.
Immutable fixtures require matching decision/dataset context and exact authored
bindings. Missing bindings produce evidence; there is no live fallback.

The planner bounds selected/all dataset cases at 10,000 and copied run evidence at
32 MiB. The source adapter imposes its own record and project limits. Request timeout
is a positive integral number of seconds capped at 600; concurrency is capped at 64.
The normal settings are 100 lifetime attempts, concurrency 2, timeout 60 seconds,
segment scheduling window 600 seconds, and at most one documented rate/overload retry.

## Ownership and state transitions

A short receipt-only read permits identical retries while an execution owner is active.
Fresh execution then acquires the OS-held project execution owner **before** source locks;
a lock-contention race rechecks the receipt without dispatch. No
network call, retry wait, or asynchronous callback runs while holding a source lock.
Only the actual owner may reconcile abandoned attempts. Merely opening a project
cannot dispatch or automatically resume. Historical completed runs are not shown as
active just because another run holds the project's execution lock.

Every attempt atomically reserves lifetime capacity and writes durable intent before
its dispatch event. The sequence is `reserved → dispatched → known|unknown|not_sent`;
a cancellation discovered before dispatch can settle directly as `not_sent`.
Process death after durable intent, dispatch, or a received but unsaved response
leaves an unknown outcome that consumes capacity. Recovery does not guess whether a
remote call happened. Failed persistence stops new dispatches; surviving in-flight
work settles where possible. Opening after recovery performs zero calls.

Documented known 429/529 responses may consume one automatic rate retry per case over
all segments. Unknowns are never automatic retries. Explicit `retry_unknown=True`
can create a new attempt, retaining the earlier unknown and consuming the same
lifetime cap. A saved valid answer is never overwritten. Provider-wide failures stop
new requests and require a new logical run rather than changing frozen configuration.

Cancellation appends a `RunControl`; no source record is overwritten. Resume writes
its new segment and acknowledged cancellation sequence atomically. Later cancellation
is still observed. Existing legacy storage cancellation flags are acknowledged only
while the execution owner is held and before dispatch. A cap extension is a durable
control, never a reset or a mutation of the original manifest.

Every segment gets the original scheduling-window duration. A monotonic deadline
includes segment commit time and is checked before reservation and dispatch. The
window stops new work; in-flight attempts finish under their aggregate request
timeout. Retry waits are interruptible. Task cancellation retains strong references
to dispatch tasks, shields settlement, releases ownership only afterward, and then
propagates cancellation.

## API and result history

`start` accepts synchronous `on_created(RunCreated)` and `on_progress(RunProgress)`
notification hooks. Resume additionally accepts `on_resumed(RunResumed)`, emitted after
the segment commit and cancellation acknowledgement with its original segment identity.
Creation is notified only after durable freeze, including a
replay flag. A failing creation hook stops before dispatch; a failing progress hook
stops new scheduling and settles existing calls. A future HTTP adapter can retain
its background task and use the creation hook to return a run ID promptly. Client
connection cancellation must not discard that retained task; durable cancellation
uses `ExecutionService.cancel`.

`show` and `list` do no provider work. `RunPage` returns items, total, and next cursor.
Safe views include caps, settings, attempts, segment timestamps, and snapshot IDs;
they exclude raw inputs, compiled bodies, responses, and credential references.
Execution exit precedence is incomplete 4, then input/response failure 3, then 0.
Ordinary incorrect predictions do not change the exit code. Reading an existing
failed run is a successful data retrieval.

A terminal event and `ResultSnapshot` are appended in one source transaction. Result
order follows manifest case order. Older snapshot IDs and bytes remain unchanged
through resume. P10 consumes frozen definition, selected and full-development
snapshots; it does not fit a baseline from current source or the test partition.
`AttemptEvent.duration_seconds` measures only the actual dispatch interval; recovery
and proven non-dispatch have no fabricated latency, and fixture timing is not live
provider evidence.

## Evidence and research

Offline tests exercise real filesystem transactions and separate OS processes:
SIGKILL at durable intent, dispatch, and received-unsaved boundaries; active-owner
contention; cancellation while settling; lifetime cap extension; callback failure;
source persistence failure; exact frozen requests; and the 12-case recovery oracle
(8 valid, 1 invalid input, 1 response error, 1 unknown, 1 pending; 10/100 attempts used).
The packaged Sandbox integration uses authored bindings, not observed Jev behavior.
No credential or inference is needed by these tests.

Primary references checked during implementation:

- [Python 3.11 asyncio tasks](https://docs.python.org/3.11/library/asyncio-task.html):
  cancellation cleanup, strong task references, `shield`, and aggregate `timeout`.
- [Python asyncio synchronization](https://docs.python.org/3.11/library/asyncio-sync.html):
  event-loop primitives do not provide cross-process ownership.
- [Python fcntl](https://docs.python.org/3.11/library/fcntl.html): OS advisory locks;
  the runner uses the existing source adapter's ownership port.

The locked environment used for implementation has CPython 3.14.7, Pydantic 2.13.5,
HTTPX 0.28.1, Typer 0.27.2, pytest 9.1.1, Ruff 0.16.10, and mypy 1.20.2. CI also checks
the project's supported Python versions. Process tests establish local filesystem
behavior on the test platform; they do not establish remote-filesystem guarantees or
live provider behavior. Live smoke verification remains separately authorized.
