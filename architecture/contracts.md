# Version 1 contracts

These versioned contracts define exact values, immutable evidence and narrow
ports shared by the working CLI and headless API. Storage, provider
HTTP and presentation adapters depend inward on these contracts.

## Dependency direction and handoff

`deykit.contracts` contains immutable Pydantic records, safe service error codes,
resource IDs, exact JSON/record codecs, schema validation, and narrow capability
protocols. `deykit.domain` contains pure definition/input/label semantics. These
modules have no HTTP, SQLite, UI, filesystem, provider SDK, or system clock dependency.
The CLI uses Typer; CLI and API adapters call the same application services.

Public imports are explicit modules, not an expanding wildcard facade:

| Owner | Stable P01 interfaces |
| --- | --- |
| Storage P02 | `contracts.codec.load_record/dump_record`; `ports.ResourceKey`, `StoredRecord`, `SourceChange`, `CommitReceipt`, `ProjectSource` |
| Authoring P03–P05 | `records.ChoiceDefinition`, `DecisionDraft`, `DecisionRevision`, `DatasetRecord`, `CaseRecord`, `DatasetSnapshot`, `LabelRecord`, `LabelChange`, `LabelSnapshot`; `domain.definitions.definition_hash`, `select_input`, `missing_options`, `label_applicability` |
| Provider P06/P09 | `ports.ChoiceCompiler` and `ProviderTransport`; `records.ProviderProfile`, `CompiledRequest`, `NormalizedAnswer`, `DispatchOutcome` |
| Runner P08 | `ports.Clock`; `records.ExecutionSettings`, `RunManifest`, `RunSegment`, `RunEvent`, `AttemptRecord`, `AttemptEvent` |
| Evidence P10–P13 | `records.CaseResult`, `ResultSnapshot`, `EvaluationRecord`, `ComparisonRecord`, `RegressionRecord`, `ReportRecord` |
| API | User JSON and previews are `JsonSource` strings; transport values retain exact source text. |

Every persisted owned record has an explicit `schema_version: 1`. `load_record`
requires the version on every nested owned record and checks JSON before Pydantic.
Persisted hashed records likewise require explicit `hash_format: deykit-json-v1`. Constructors default version
for new records. Unknown fields, unsupported versions, and wrong types fail. Arbitrary
JSON metadata is an explicit validated source string. Nested owned records and tuples
are frozen; `JsonDocument.value` returns a new tree each time. Do not use Pydantic's
unvalidated `model_construct` or `model_copy(update=...)` for application mutations.
Create a newly validated record instead. Cross-record IDs, snapshot scope, manifest
hashes, and lifecycle transition checks belong to their application owner; these
records do not pretend to implement storage or execution.

A draft stores unrestricted editor source and can be syntactically incomplete. Only
`ChoiceDefinition` is runnable: one choice question, at least two unique options,
nonblank instructions, valid declared schema and explicit selected fields. Text case
input is a JSON string in `input_source`; JSON case input is a JSON object. Full input
validation happens before field selection. Labels never belong in model state.

IDs are 1–128 ASCII alphanumeric/underscore/hyphen characters, starting alphanumeric.
Windows reserved devices are rejected case-insensitively, as are paths, dots, percent
encoding, whitespace and Unicode. Display names remain Unicode and editable. ID
validation is not a substitute for P02/P15 symlink/root containment checks.

Label provenance is `human`, `authored_fixture`, `imported_unknown`, or
`model_generated`. Stored status is `active` or `disputed`; stale/incompatible causes
are derived together and remain visible. Renames preserve option IDs and expectations;
removed IDs are returned explicitly rather than deleted from old labels/regressions.

## Exact JSON and hashing

`parse_json(str|bytes)` returns bool/null/string/Decimal/list/dict without coercion.
Both JSON integer and fractional tokens become exact Decimal values. Construction
never uses a float. `dump_json` emits the shortest of normalized plain, scientific, and integer-coefficient exponent numeric
JSON tokens (scientific wins ties) and retains insertion order;
`canonical_bytes` sorts object keys by Unicode code point. Arrays retain order;
strings retain their exact Unicode without normalization. Controls use JSON short
escapes where defined, otherwise lowercase hex; slash and Unicode are not escaped.

For `deykit-json-v1`, finite nonzero numbers have one leading digit, no insignificant
trailing fractional zeros, lowercase `e`, and an unpadded exponent with no plus sign.
Zero, including negative zero, is `0`. Wire spelling is derived from the same
normalized digit tuple; equivalent numeric values have deterministic wire spellings
independent of Decimal precision or capitals settings. Normalization uses the Decimal digit tuple,
not context-sensitive arithmetic. `semantic_hash` hashes UTF-8
`deykit-json-v1\n` followed by canonical bytes. `bytes_hash` is ordinary SHA-256 over
exact dispatched bytes with no prefix or canonicalization. Object semantic equality
can coexist with different request hashes. Source preservation is a separate claim.

Limits are 1,048,576 UTF-8 source bytes, 64 container levels, 100,000 value nodes,
4,096 coefficient digits, explicit and effective nonzero scientific exponent magnitude at most 10,000 and exponent
lexeme length at most seven characters. Keys count toward source bytes but not value
nodes. These are deliberate profile limits; excess is `json_resource_limit`.
The effective exponent bound closes accepted values under canonicalization.
Derived canonical/wire output has a separate 2 MiB, 128-level, 200,000-node budget
(`GENERATED_LIMITS`) to allow scientific spelling and request wrappers. Parse generated
request bodies with that budget, not user admission defaults. Minimal wire spelling
ensures selecting fields from an admitted user document does not expand its size.
Owned record envelopes have a separate 16 MiB, 256-level, 1,000,000-node budget
(`RECORD_LIMITS`), allowing source strings and generated request bodies to be escaped
inside records. Every user `JsonSource` still independently has the 1 MiB admission
limit. Aggregate dataset/result snapshots that exceed the envelope budget fail with
`record_resource_limit`; the storage/run owner must preflight persistence before inference.
Report envelopes alone allow 40 MiB, with the same depth and node bounds.
Their owned content allows 32 MiB and 750,000 values. Comparison outcome sources
allow 4 MiB and 200,000 values. These budgets do not change exact numeric
encoding, hashes, ordinary record admission or individual user-source limits.
Duplicates (including escaped equivalent keys), nonfinite numbers, malformed UTF-8,
unpaired surrogates and unsupported Python types such as float are rejected.
The immutable source wrapper and `JsonSource` fields prevent default Pydantic Decimal
serialization from changing numeric user values into strings.

`definition_hash` includes stable question/option IDs, instructions, option order,
names/descriptions, selection and parsed schema semantics. Notes/save times live
outside the definition. Case input identity is `JsonDocument(input_source).content_hash`,
excluding tags/splits/annotations. Snapshot owners define their complete frozen hash
projection, persist its named profile, and validate cross-record consistency.

## Schema validation

The validator implements Draft 2020-12 using jsonschema 4.26.0. Integer means an exact
mathematical integer (including `1.0`), excluding booleans. Exact `multipleOf` uses
rational integer arithmetic; bounds compare exact numeric values. The full declared
input is validated before selection. Remote/relative `$ref` and `$dynamicRef` are
rejected and registry retrieval is disabled as a second defense. Local fragments targeting declared schema positions/anchors are
supported; references into custom annotation data are rejected. Same-dialect markers
are validated and removed only from schema positions so nested validation retains
exact-number semantics; missing/recursive references fail visibly. Version 1 rejects `$id` scope
changes and alternate dialect declarations. `format` remains Draft 2020-12 annotation
behavior; arbitrary custom keywords are not invented validation rules. Errors expose
keyword/path information, not whole input documents.

## Storage and execution boundary

`ResourceKey(collection, resource_id, scope=())` retains visible IDs and safe parent
scope separately: cases use `(dataset_id,)`, labels use `(decision_id, dataset_id)`,
revisions use `(decision_id,)`; global resources use `()`. Every component has the
same portable validation. `list_ids(collection, scope=())` stays within that scope.

`ProjectSource` reads from authoritative source after pending recovery; `consistent_read`
holds a consistent source boundary across reads. `commit(operation_id, changes)` owns
one recoverable atomic multi-record operation. `expected_etag=None` is create-only;
otherwise the exact byte ETag must match. A `body=None` change deletes an existing
record. Append history and reservations create new immutable keys with create-only
expectations. A repeated operation ID with identical content returns its original
receipt; changed content conflicts. Listing is deterministic. P02 owns durable journals,
short source locks, execution ownership, recovery and index invalidation, not P01.

`CompiledRequest` freezes adapter/compiler/version/requested model/destination/exact
UTF-8 JSON body bytes and checked SHA-256. Optional `semantic_headers_source` freezes
non-secret transport semantics; Jev admits only its exact image opt-in header.
The empty value is omitted on serialization, preserving existing text records,
fixture hashes and review identities. Nonempty headers participate in fixture and
review hashes and exact request matching. Provider credentials are injected privately
by transport and never persisted in requests. A profile holds only an
external credential reference; P09 validates its syntax and endpoint constraints.
The pure compiler takes a validated definition, already selected exact state, and
profile. Response validation uses the frozen request. One async `dispatch` returns
known/unknown/not_sent with one answer or safe error. Unknown is never retryable;
retry-eligible known rejection remains a runner decision. Native probabilities,
confidence, reported model, raw response and usage may be absent and remain distinct.

`ImageChoiceCompiler` adds named, admitted image assets to compilation without local
file access. Jev uses prepared PNG/JPEG bytes in base64 JSON with collision-checked
references. Image requests have an 8 MiB JSON bound; text retains its 2 MiB generated
bound and user JSON admission remains unchanged. Image format, dimensions and bytes
are checked again before transport. Frozen case assets retain source and preparation
identities independently of the wire body.

`ServiceError` carries a stable code, safe identifier/row/reason, and fixed message;
`safe_dict()` is the public error envelope projection. Never attach raw exceptions or
Pydantic input values. `Success[T]` and `Failure` are transport-independent envelopes.
CLI/API owners map domain codes and execution exit precedence to their surfaces.

## Primary references and tested tools

Checked 2026-10-05: [Python Decimal construction/context](https://docs.python.org/3/library/decimal.html),
[jsonschema validator/type extensions](https://python-jsonschema.readthedocs.io/en/stable/validate/),
[Pydantic serialization](https://docs.pydantic.dev/latest/concepts/serialization/).
The repository locks Pydantic 2.13.5, jsonschema 4.26.0, referencing 0.37.0,
Typer 0.27.2 and HTTPX 0.28.1 for the forthcoming provider owner. OS keyring 25.7.0
is an optional extra. Runtime dependency ranges are compatible constraints; `uv.lock`
is the reproducible development environment. Documentation research is not provider
compatibility evidence.
