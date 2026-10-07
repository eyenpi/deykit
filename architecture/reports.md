# Immutable evidence reports

`ReportService.create(request, operation_id=...)` saves an immutable report for a
run, evaluation, comparison, diagnostic group, or regression-check group. Group
targets require an explicit `diagnostic` or `check` kind and may pin a
`group_snapshot_id`; the default chooses the latest valid matching snapshot in
one captured source epoch. Group projection reads the accepted P12 pinned
snapshot readers and does not create P10 evaluation records or aggregate metrics.
Core run/evaluation/comparison selection remains unchanged. If a selected run
result has no original evaluation, creation delegates to the saved-answer
evaluation service. Report creation makes no provider calls.

`read(report_id)` admits the saved report against its immutable evidence.
`metadata(report_id)` and `list(cursor=..., limit=...)` return metadata without
raw material. `render(report_id, format="json" | "markdown")` produces exact,
deterministic UTF-8 bytes. `export(report_id, format=..., destination=...,
writer=...)` sends those detached bytes through the neutral
`contracts.artifacts.ArtifactWriter` port after releasing the source boundary.
Exports retain the saved report identity and typed destination outcome for
retry.

Raw inputs, prepared request bodies, and stored response material are excluded
by default. `RawChoices` controls the three categories independently. Structured
values pass through the pure sanitizer; original evidence hashes remain bound
alongside sanitized-copy hashes. The sanitizer does not recognize arbitrary
unknown plaintext secrets.

The pure opaque-response projector also supports byte evidence by sanitizing
before encoding, preserving exact byte hashes, and choosing UTF-8 or padded
base64. Current persisted attempt outcomes expose JSON response source strings,
so the service does not invent opaque response bytes or claim that such bytes
are available from saved records.

The v1 report hash covers the profile, immutable link lists, nullable group
snapshot links, raw choices, and exact content. Group reports retain ordered
member run/result/label context, group and snapshot hashes, the exact segment,
and diagnostic or check evidence. Check rows bind original regression content
hashes. Content is limited to 1 MiB and
rendered artifacts to 8 MiB; neither is truncated. These hashes bind saved
evidence to its referenced records; they are not author signatures. JSON and
Markdown preserve saved denominators, null reasons, partial outcomes, fixture
status, and comparison buckets. Markdown places all source contexts before
result IDs and keeps each evaluation's class, confusion, baseline, latency/usage,
and case sections in a fixed order. Group summaries and pinned member context
precede raw material. Diagnostic counts retain the original-case denominator;
check rows retain null outcomes and the frozen regression selection reason.
Raw JSON source remains unchanged; Markdown
normalizes line endings in its rendered copy. Fixture evidence is authored
software-verification material, not provider-quality evidence.
