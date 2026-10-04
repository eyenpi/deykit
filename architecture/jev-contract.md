# Jev choice adapter contract

Primary documentation refreshed 2026-10-05. This is a software mapping contract; the authored corpus is not observed provider behavior or quality evidence. No credentials or paid inference were used to prepare it.

## Sources and scope

- [API reference](https://docs.typesafe.ai/api): bearer-authenticated POST to `https://api.typesafe.ai/v1/systemone`, keyed questions and answers, at most 255 choice criteria, required model/usage/choice/probabilities/confidence, and HTTP 401/422/429/529 meanings.
- [Structured criteria](https://docs.typesafe.ai/primitives/advanced): criteria can contain JSON objects.
- [Models](https://docs.typesafe.ai/models): current pinned ID `jev-1.13.0`; requested aliases and returned versions are distinct evidence. GET `/v1/models` lists model records with name, description and release_date. Versioned IDs may work without appearing in that list. Documented token limits are not a locally verified tokenizer bound.
- [Confidence](https://docs.typesafe.ai/confidence): confidence is provider-defined; retain it independently of correctness, with no fabricated replacement.
- [HTTPX transports](https://www.python-httpx.org/advanced/transports/) and [API](https://www.python-httpx.org/api/): explicit transport retries and redirect controls. Deykit owns one network dispatch per transport invocation; the runner alone schedules another attempt.

## Compiler v1

One validated choice definition and already-selected text/JSON state compile through the shared exact JSON codec. The wire object insertion order is state, model, questions. Its sole question uses the stable question ID; fields are type, instructions, criteria. Criteria preserve frozen option order and stable IDs. Each value contains name then description, with JSON null when absent and an empty string preserved when explicitly supplied. Labels and case metadata are outside this input port. Preserve exact UTF-8 body bytes and their SHA-256, requested model, destination, adapter and compiler identity. A fixture compiler uses the same shape and an explicit authored model identity without transport. Wire identity changes require new fixture bindings.

## Response v1

Require exactly the requested question, type choice, a known selected option, all and only expected probability IDs, native confidence, actual model identity and both nonnegative integer token counts. Numbers must be finite; probabilities and confidence must be in [0,1]. Probability sum and selected-option argmax allow absolute tolerance 0.000001, without normalization or replacement. Booleans and numeric strings do not count as numbers. Duplicate keys and malformed source JSON fail through the shared codec. Additional top-level metadata may be ignored safely, but no provider body or headers enter errors. Alias movement remains visible as requested versus actual model; a concrete requested version mismatch fails validation.

## Transport and credentials

Only the exact official HTTPS inference/models destinations are permitted. No authenticated redirects, environment proxies, SDK retries, hidden client retries, or response-body interpolation into errors. HTTP 401/403 is provider-wide authentication failure; 422 is provider-wide payload failure; 429/529 is a definitive rejection eligible for runner retry. All other server errors, timeouts and disconnected responses conservatively retain unknown execution outcome. HTTP redirects are rejected. Retry-After supports nonnegative seconds or HTTP dates using an injected/current UTC clock. Configuration and credential status never send network requests. Model listing is explicit GET and performs zero inference.

Profiles contain environment variable names or OS-store references, never values. Credentials resolve only at dispatch (or explicit local credential status). Safe errors have static messages; sanitization removes credential strings and authorization/header-like fields recursively. Authenticated response fields are sanitized before any retained evidence. OS-store support uses an injected backend so tests never unlock or alter the real store.

## Evidence limits

`tests/providers/corpus` is manually specified synthetic wire data, including a valid choice response and malformed variants. Offline tests can establish exact compilation, strict rejection, no hidden retry, and local redaction. They do not establish provider availability, preprocessing/order preservation, real OS-store integration, live latency, billing, or decision quality. Runner and CLI/API integration are separate acceptance gates; a standalone transport cannot claim run budget, cancellation, retry or smoke-cap enforcement.

## Implemented interfaces and verification (2026-10-05)

- `JevChoiceCompiler` implements shared `ChoiceCompiler`; `compile_choice` also supports `adapter="fixture"`, destination `fixture:jev-choice`, and an explicit authored requested model. `CompiledRequest` contains compiler `jev-choice`, version `1`, exact bytes and SHA-256. The selected-state port accepts the declared JSON fields with nested exact values; an empty selection preserves the entire validated input object, matching domain.select_input.
- `JevProvider` implements asynchronous shared `ProviderTransport.dispatch` with native HTTPX AsyncClient/AsyncHTTPTransport. An asyncio aggregate deadline bounds connect, headers and body in addition to HTTPX phase inactivity timeouts. Internal expiry reports unknown execution; external task cancellation propagates after async response/client cleanup, so the runner must preserve unknown dispatch evidence. Transport contains no retry loop. `models()` is also async and uses the same deadline. See [Python asyncio timeouts](https://docs.python.org/3.11/library/asyncio-task.html#timeouts) and [HTTPX async resource lifetimes](https://www.python-httpx.org/async/).
- `ProviderProfiles` uses `ProjectSource` for conflict-aware configure/read/list; the source owns locking, recovery and operation-ID behavior. `Credentials` resolves `env:NAME` or `keyring:SERVICE/ACCOUNT`. `os_secret_store()` explicitly selects only a native backend from the installed keyring library; it rejects plaintext/custom/chained backends. Injected fake stores are used in tests. [Keyring primary documentation](https://keyring.readthedocs.io/en/latest/) describes its backend/configuration behavior.
- `JevProvider.models()` performs one explicit GET. `preflight()` checks local credential availability. No smoke entry point bypasses the runner.

Tested locally on macOS with CPython 3.14.7, httpx 0.28.1, httpcore 1.0.9, Pydantic 2.13.5, pytest 9.1.1, and keyring 25.7.0 installed. `uv sync --locked` base install: 218 tests passed, one optional native-backend test skipped; 117 provider tests passed with that same skip. Full Ruff (including format), strict mypy, builds and clean wheel/sdist installation checks passed against main `4f802fa`. The optional keyring import uses a lazy runtime boundary, so base-install typing does not require the extra. OS-store tests use a fake backend and do not establish real keychain permission/unlock behavior. Full smoke cap, retry scheduling, provider-wide stopping, CLI/API commands and live compatibility remain pending integration gates.

HTTPX/httpcore DEBUG header traces were independently exercised over an offline fake network byte stream. A context-local filter suppresses these library records during authenticated operations because server headers can echo credentials; unrelated caller logs retain their configuration. No raw response headers are retained.

The reviewed foundation emits the shortest deterministic exact numeric wire tokens (scientific wins ties); canonical semantic hashes keep their separate format. Request parsing uses its 2 MiB generated-output budget, including wrapper depth, while raw response evidence remains within the 1 MiB source budget. Maximum admitted text/deep JSON request vectors and redaction-expansion rejection are tested. Provider keys use the empty/default ProjectSource scope.

Independent review regressions cover full-object empty field selection; typed question/probability keys named headers, authorization, secret and api_key; actual credential strings in typed IDs/metadata; definitive 401/403/422/429/529 headers with oversized/disconnected/timeout bodies (zero body reads); aggregate 60-second expiry after two individually timely 30-second reads using a virtual event-loop clock and the real HTTPcore parser; connect/header/body deadline cleanup; and explicit cancellation cleanup. Error payloads are never needed for status classification and are not read.
