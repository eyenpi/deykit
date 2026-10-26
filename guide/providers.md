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

## Jev images

Import [managed local images](imports.md#managed-local-images), then select their
names in the saved decision definition, for example `"selected_images":["product"]`.
Selection opts into Jev's experimental image API. The compiler includes the
prepared bytes and the required `TypeSafe-Danger-Zone-Images: true` header.
`run --dry-run` shows this header in `semantic_headers_sources` and performs no
inference. A text-only decision sends no image header or assets.

For JSON input, selected image names become additional top-level state fields;
existing selected JSON fields keep their values. For text input, the original
string becomes `state.text`. Each image field contains a generated reference to
the top-level `assets` map. For example, select `product` and refer to `product`
in the question instructions. Names cannot replace an existing state field
(`text` is reserved for text input). Generated references never match existing
input, instructions, or option text. Labels and local paths stay outside the request.

The [provider image contract](https://docs.typesafe.ai/images), checked on
22 October 2026, supports still PNG/JPEG images with each side between 280 and
1568 pixels. Jev 1.13 and 1.14 support images; aliases may change over time.
Preview rejects missing images, WebP, incompatible dimensions, and invalid bytes
before dispatch. Deykit does not resize or convert them during compilation.
Use explicit import preparation for padding, or prepare a suitable source file.
Metadata, including EXIF orientation, is preserved in the submitted bytes;
the provider does not apply EXIF orientation, so prepare upright pixels yourself.

Deykit retains its 4 MiB limit per managed image and bounds the compiled base64
JSON request at 8 MiB, within its portable record envelope. The existing 32 MiB
aggregate run-plan limit still applies, including embedded image requests; split
larger cohorts into bounded runs. These local limits are below Jev's transport
limits. Provider-side re-encoding and context limits can still reject a request.
Jev HTTP 400 and 413 responses are recorded as known, nonretryable rejections
of that case. Other cases continue within the run's existing attempt budget.

Use the normal bounded `run --mode live` workflow after reviewing the dry run.
The frozen request retains exact prepared bytes and semantic headers, and the
preview hash binds both. Unknown outcomes require explicit resume; resume uses
the frozen transport without reading the original local files. Use
`results show RUN_ID CASE_ID --request --attempts` to inspect the body and semantic
headers. Authored fixture bindings also include header identity and remain
authored evidence. Image requests use the same strict model, question, choice,
probability, confidence, and usage validation as text requests.

## OpenAI Decisions

Configure the native Decisions adapter with an explicit model:

```sh
uv run deykit --project /absolute/study --json provider configure openai-main \
  --adapter openai --model gpt-6-luna
uv run deykit --project /absolute/study --json run \
  --decision DECISION_ID --revision REVISION_ID --dataset DATASET_ID \
  --mode live --provider openai-main --case CASE_ID \
  --attempt-limit 1 --concurrency 1 --rate-retries 0 --dry-run
```

The shorthand saves `env:OPENAI_API_KEY`; `--credential-env NAME` selects another
reference. Configuration, local credential operations and preview make no network
request. After reviewing the preview, an explicitly authorized run uses the same
arguments without `--dry-run` and with a saved `--operation-id`. The existing run,
cancel, explicit resume, comparison and report workflows apply. Model listing and
`doctor --network-check` are not supported for this adapter: the general OpenAI
model catalog does not establish Decisions compatibility. `doctor --live-smoke`
is supported and is an inference action.

The [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) and
[API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create),
checked on 23 October 2026, document `gpt-6-luna` as the supported model. Deykit
accepts that exact identity and sends only to `https://api.openai.com/v1/decisions`.
Other models, destinations, predicates and scores are outside this adapter's
choice-classification scope. Preview enforces the 2–255 choice limit. Each stable
Deykit option ID is the provider's string `value`, in the requested option order;
its name and nonempty description are joined with a newline for the provider's
`description`. Question ID and instructions are preserved. Responses map by
value, so reordered probability entries cannot change option identity.

Text is sent as text. Selected JSON fields are sent as one user `input_json`
part, preserving exact numbers and nested values. JSON input has the API's
256 KiB, 32-container-depth and 10,000-value bounds. JSON keys such as `role` or
`image_url` remain data. Unselected fields and labels stay outside the request.

Select [managed images](imports.md#managed-local-images) using `selected_images`
on the saved definition. The compiler adds each selected image in order, preceded
by `Image: NAME`, with its prepared bytes in a base64 data URL and `detail: auto`.
No local path or remote URL is sent. PNG, JPEG and WebP must be still images;
compilation checks their decoded format and dimensions without transforming them.
Existing local limits apply: 4 MiB per image, 8192 pixels per side, 16 million
pixels, 8 MiB per compiled image request, and 32 MiB per run plan. Split larger
cohorts into bounded runs. Preview rejects unsupported or oversized requests
before dispatch; provider acceptance can impose additional constraints.

The compiler identity is `openai-decisions-choice` version `1`. Frozen image
requests declare `body_kind: image_json` to retain the larger request budget
without adding provider headers. Old requests omit this field and keep their
existing interpretation. Older builds cannot execute this new adapter; retain a
compatible reader for projects containing its runs. No project migration is needed.

Answer validation checks the named question, type, exact requested/reported model,
choice identity, complete probability vector, finite values in [0, 1], sum and
argmax within 0.000001, and separate native confidence. Probabilities are never
normalized. A refusal becomes a final `response_error` with reason
`provider_refusal`; it is neither an unknown outcome nor automatically retried.
Other cases can continue. Strict reports count refusals as failed answers.
New classification reports also count explicit refusal markers among applicable
expectations. Other response errors may include unmarked refusals, so the count
does not establish their absence. Saved v1 reports retain unavailable refusal
counts. See [classification reports](reports.md#classification-experiment-preset).
Invalid answers, model mismatches and refusals retain sanitized response evidence
and valid usage.
Syntactically invalid JSON, duplicate keys and invalid UTF-8 retain a
`deykit_unparsed_response` envelope containing a diagnostic text excerpt, not
exact wire bytes or a parsed answer. JSON escapes are decoded before removing
known credentials and Bearer tokens; invalid UTF-8 and lone surrogates are
replaced. Normalization, replacement and truncation are explicit. At most 150,000
UTF-8 bytes are captured, leaving room for JSON escaping under the existing 1 MiB
response-source bound. Capture counts and hash describe the sanitized text at
capture time; later report redaction uses the report's outer identity metadata.
The text remains visible to additional inspection/report sanitizers. Arbitrary
unknown secrets cannot be recognized in an unparsed body. Default reports still
omit response content.
Unknown or invalid usage stays unavailable. Cache counters stay within total
input usage and are never added again; existing token-list estimates do not model
cache discounts and are not billed cost.

A known HTTP rejection is not retried except for the runner's bounded rate-limit
policy. Timeouts and disconnections remain unknown and require explicit
`--retry-unknown` to resume. Authentication, unavailable-model and unexpected HTTP
statuses (including 5xx and redirects) stop further scheduling and require a new
run under the existing provider-wide failure policy. A 5xx or redirect outcome
remains unknown; a new run can duplicate a remotely completed request and needs
renewed scope review. Transport redirects and ambient proxy settings are disabled.
Offline tests exercise the real CLI and runner with an authored HTTP transport;
they do not establish live access, provider acceptance or model quality.
