# Provider profiles and diagnostics

Provider profiles are local, non-secret configuration. Set `--project PATH` on
the root command or run inside a project. `--json` produces one safe versioned
result on stdout; a validation, conflict, missing credential, or failed
diagnostic exits 2. Profile creation and reading make no provider request.

```sh
uv run deykit --project ./study --json provider configure jev-main --adapter jev --model jev-1.13.0
uv run deykit --project ./study provider list --limit 25
uv run deykit --project ./study --json provider show jev-main
uv run deykit --project ./study --json credential status --provider jev-main
uv run deykit --project ./study --json doctor
```

The Jev shorthand stores `env:JEV_API_KEY` by default. Set the variable in the
process environment before an explicit network action; the value never enters
the project. `--credential-env OTHER_NAME` saves another environment variable
name without reading it. A UTF-8 `ProviderProfile` record can instead be
provided with `--file PATH` or `--stdin`, including an explicit absent
`credential_ref`. File and shorthand options cannot be combined.

```sh
uv run deykit --project ./study --json credential set --provider jev-main --env OTHER_NAME
uv run deykit --project ./study --json credential forget --provider jev-main
```

`credential status` checks availability locally and returns only a boolean.
`credential forget` unlinks an environment reference; it cannot unset the
external variable. To use the approved native OS secret store, `credential set
--provider jev-main --stdin` reads a key from stdin, or `--prompt` opens a
hidden prompt on a terminal. There is no secret-value argument. If the native
store is unavailable, the command fails safely; use an environment reference.
The optional `keyring` package and an approved operating-system backend are
required for native storage. Project export/copy contains only references, so
the destination machine needs its own credential. Avoid shell history and
terminal recording when provisioning values.

For scripted retry, supply `--operation-id ID` and `--if-hash ETAG` from
`provider show` to a configuration or credential mutation. A retry with the
same intent and original precondition returns its original receipt after
later edits; a changed intent conflicts. Without a pinned ETag, a retry may
read the newer profile and conflict. Native secret storage and the portable
project source are separate stores, so a concurrent edit or source failure
can require repeating a failed credential operation.
If native deletion succeeds before a source write fails, repeating `credential
forget` can finish unlinking the reference after a healthy backend read confirms
the secret is absent. An inaccessible backend still fails and retains the
reference.

Explicit diagnostics are the only commands here that contact Jev:

```sh
uv run deykit --project ./study --json provider models jev-main
uv run deykit --project ./study --json doctor --provider jev-main --network-check
```

These perform one authenticated model-list GET and no inference. The listed
aliases do not prevent a documented pinned model ID from being configured.
`doctor` alone checks local project integrity and configured profiles without
network traffic. Use a fixture profile (`--adapter fixture --model
authored-demo`) only for authored fixture runs; it has no credential or live
destination. Fixtures remain authored test evidence, not observed provider
quality.

An explicit one-case live smoke is available with the runner integration:

```sh
uv run deykit --project ./study --json doctor --live-smoke --provider jev-main --decision DECISION_ID --dataset DATASET_ID --case CASE_ID
```

It uses the same execution service as `run`, allows one attempt with concurrency
one, a fixed 60-second timeout and scheduling window, and no retry. It reports a
durable run/result identity with requested model, settings and attempt count.
`--network-check` and `--live-smoke` cannot be combined. Supply an explicit
`--operation-id ID` to recover the original smoke evidence without dispatching
again; a changed scope using that ID conflicts. A response or adapter failure is
evidence of that specific attempt,
not a quality verdict. This is a paid inference action; run it only with the
intended case and available credential.
