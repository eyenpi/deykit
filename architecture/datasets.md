# Dataset aggregates and import transactions

`DatasetService` and `ImportService` depend on `ProjectSource`, `Clock`, and an injected ID factory. Domain mapping and label identity have no transport, filesystem, database, or provider dependency. These services are suitable for the later CLI/API adapters; this change does not register those adapters.

Every dataset mutation creates a new `DatasetRecord.revision_id`. The record ETag therefore acts as the aggregate concurrency token for case edits as well as dataset metadata. Legacy records may omit the pointer; their next mutation creates one. Case mutations require the expected dataset ETag; editing/removing a case also requires its own ETag. List ordering and cursors use stable IDs, with a page limit of 1–500. Names never select an identity. Case input, tags, split, group, derivation and metadata are separate fields. Shared cases are not discarded simply because another decision cannot consume them.

All mutation paths look up the operation ID and intent hash while holding `consistent_read`, before current-state validation, generated IDs or timestamps. Repeating an identical operation returns the original committed result even after later changes. Reusing its ID for another intent conflicts. The filesystem source journal retains durable before/after records and revisions outside SQLite; the dataset revision pointer is not a duplicate history store.

Removing a current case clears its current labels across all decisions in the same transaction and appends `clear` label changes. Immutable dataset snapshots and old operation history remain unchanged. Adding the same case ID again starts without current labels. Archiving a dataset hides it from the default list and blocks case/import mutations; restore preserves its identity.

## Import context and identity

A frozen preview contains the exact source text, its byte hash, explicit versioned mapping and semantic hash, stable row IDs, physical source lines, proposed case records, expected option IDs, exclusions, semantic duplicate IDs, dataset ETag, chosen decision context and a preview hash. Preview performs no source writes, clock calls or generated-ID calls. Automatically assigned case IDs derive from dataset, source hash, mapping hash and row number, so preview and commit use the same identity.

The default decision context is the validated current editor draft. Syntax-invalid or incomplete drafts cannot silently fall back to a saved definition. Callers can explicitly select an immutable revision by ID. The preview fingerprints the dataset, every current case, decision pointer, selected draft or revision, and relevant current labels. Commit rechecks those bytes under the source lock, recomputes the preview, and rejects altered context or altered preview contents. Re-reading source fingerprints also detects external file changes that did not update the dataset pointer; unrelated external editors must still respect the project lock for atomic cooperation.

Input schemas and selected-field semantics come from `domain.definitions.select_input`. The stored case retains its full exact input. Expected answers and metadata cannot share mapped source columns with input, including via field aliases. Expected option names require an explicit alias to an option ID; otherwise only exact IDs are accepted. Imported provenance is `imported_unknown`, never inferred to be human.

Current label identity is `label-` plus `deykit-json-v1` semantic hash of `[case_id, question_id]`, scoped by `(decision_id, dataset_id)`. P05 must reuse `domain.label_identity.label_id`; the case/question tuple encoding prevents delimiter collisions. Imported cases, current labels, append-only label changes, and the new dataset revision commit in one recoverable transaction.

Any invalid row aborts a default commit with zero writes. Explicit `skip_invalid=True` commits only the valid rows and returns exact excluded rows/reasons. ID conflicts are invalid; identical semantic input under different IDs is retained and flagged. A partial import with no valid rows is rejected.

## Parsing and limits

The [Python CSV documentation](https://docs.python.org/3.11/library/csv.html) defines ordinary reader fields as strings; Deykit uses strict `csv.reader` with [`StringIO(newline="")`](https://docs.python.org/3.11/library/io.html#io.StringIO) and never `QUOTE_NONNUMERIC`. JSON decoding is enabled only by explicit mapping flags. JSONL and decoded cells use the shared strict exact codec: duplicate keys, nonfinite numbers, invalid UTF-8 and unpaired surrogates fail. LF/CRLF delimit JSONL rows; Unicode line/paragraph separators inside strings remain data. Source byte order marks are rejected explicitly. Numeric values preserve arbitrary exact decimal precision through source strings, without Python float or Pydantic Decimal serialization.

Imports are capped at 8 MiB and 10,000 logical rows. Shared JSON per-value/record limits still apply. CSV uses the interpreter's existing field limit (131,072 characters in the verified environment) without mutating that process-global setting. Lexical CSV errors or field-limit failures abort preview because reliable row boundaries cannot be promised. Well-formed CSV rows with the wrong number of cells remain explicit invalid rows. `source_line` records the ending physical line of a CSV record, including multiline quoted fields.

## Evidence

Authored offline fixtures cover the A09 ten-row oracle (row 3 required input missing; row 7 unknown option), A10 identity conflicts and duplicate inputs, and A11 selected model input excluding expected values and metadata. Tests use the real filesystem source and cover recovery at prepared/decided/partially applied transaction checkpoints, concurrent preview conflicts, manually edited source, malformed data/mappings, precision and replay interleavings. These are automated filesystem/service observations, not UI, platform, or live provider evidence.
