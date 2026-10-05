# Provider configuration boundary

`ProviderProfiles` is a local application service over `ProjectSource`. It
admits Jev profiles through the live adapter validator and authored fixture
profiles through the fixture validator. Neither path resolves credentials or
imports the HTTP transport. The CLI's `provider configure` and `credential
set/forget` commands use the same service, durable operation receipts, source
ETags, and stable intent hashes. A credential-reference mutation hashes the
reference and original precondition before merging omitted profile fields, so
a completed operation can replay after a later profile edit.

`credentials_for(frozen_profile)` is the narrow runner composition port. It
reads the reference kind but defers value resolution until explicit status,
preflight, dispatch, or model listing. Environment references never load the
optional keyring package; OS-store references request an approved native
backend lazily. An unavailable backend yields a safe missing-credential
preflight. Profiles, project records, output envelopes, and operation intents
contain references only. CLI `credential status` deliberately reveals only
availability, never a value.

The CLI keeps network access behind `provider models`, `doctor
--network-check`, and `doctor --live-smoke`. The first two call the adapter's
single GET model-list method and have zero inference calls. Smoke delegates to
`ExecutionService`; its one-case request has a lifetime attempt cap of one,
concurrency one, a fixed 60-second timeout/deadline, and no automatic retry.
Run evidence retains the adapter,
requested/actual model, and result state. Nothing in local configuration or
help initializes an HTTP request or resolves a credential.

Offline tests cover installed CLI project/profile lifecycle, fixture/live
separation, source replay and stale preconditions, fake model-list transport,
safe missing keyring, and a runner-backed fake smoke with at most one dispatch,
including rejection, malformed response, timeout and disconnect with idempotent
evidence replay. Tests use fake environment values and injected HTTP transports.
These checks establish local behavior only. Native OS-store availability and
real Jev compatibility require separate platform/live evidence.

The diagnostic mapping was rechecked on October 5, 2026 against the official
[API reference](https://docs.typesafe.ai/api) and
[model documentation](https://docs.typesafe.ai/models). Offline verification uses
the locked HTTPX 0.28.1, Typer 0.27.2 and Pydantic 2.13.5. Documentation research
and fake transport responses do not establish authenticated live compatibility.
