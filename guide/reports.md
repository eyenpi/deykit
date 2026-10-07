# Evidence reports

The Python `ReportService` saves a fixed view of a run, evaluation, comparison,
diagnostic group, or regression-check group. Later run resumes and edits to
labels, regressions, or decision drafts do not replace saved evidence. Report
creation and rendering make no provider calls. Diagnostic and check reports use
the group's pinned snapshot and create no P10 evaluations or aggregate metrics.
When a selected run result has no original evaluation, the service evaluates
the saved answers against their original labels.

Create with `ReportService.create(ReportRequest(...), operation_id=...)`. Read
the complete saved report with `read(report_id)`. Use `metadata(report_id)` or
`list(cursor=..., limit=...)` for metadata only. Render as JSON or Markdown with
`render(report_id, format="json")` or `render(report_id, format="markdown")`.
To write an existing report, call `export(report_id, format=..., destination=...,
writer=...)`; a failed destination write keeps the report available for retry.

The installed CLI exposes the same service for local exports and metadata:

```text
deykit [--project PATH] [--json] report export TARGET_ID --output FILE [--format json|markdown]
deykit [--project PATH] [--json] report export TARGET_ID --target-kind run --evaluation ID --output FILE
deykit [--project PATH] [--json] report export TARGET_ID --target-kind run --result-snapshot ID --output FILE
deykit [--project PATH] [--json] report export TARGET_ID --target-kind diagnostic --group-snapshot ID --output FILE
deykit [--project PATH] [--json] report export --report-id REPORT_ID --output FILE [--format json|markdown]
deykit [--project PATH] [--json] report show REPORT_ID
deykit [--project PATH] [--json] report list [--cursor ID] [--limit 50]
```

For a new export, pass exactly one target ID or `--report-id`. New targets can
select `--target-kind run|evaluation|comparison|diagnostic|check`, and accept
`--evaluation`, `--result-snapshot`, `--group-snapshot`, and `--operation-id`
selectors. The three independent `--include-raw-inputs`,
`--include-raw-requests`, and `--include-raw-responses` switches default off.
Saved-report exports use the frozen raw choices and reject creation selectors.
Use `--output`, `--destination`, or `-o` for the local file. JSON mode prints
one versioned envelope containing export metadata; report content is written
only to the requested file. A failed destination returns the saved report ID
and artifact metadata, prints a safe error, and exits with code 2 so the same
report can be exported again. A successful write with a durability warning
keeps exit code 0 and includes the warning in the JSON envelope or on stderr.
`report show` and `report list` return metadata only.

Group reports need an explicit target kind:

```python
ReportRequest(target_id=group_id, target_kind="diagnostic")
ReportRequest(target_id=group_id, target_kind="check", group_snapshot_id=snapshot_id)
```

Omitting `group_snapshot_id` selects the latest valid matching snapshot from a
single captured source view. A pinned snapshot keeps its original member
results across later resumes. Diagnostic reports show seed, requested and
actual option orders, the independent case denominator, and observed outcomes.
Check reports retain each original regression hash, expected and actual answer,
nullable pass state, provenance, split, and the frozen baseline reason.

Raw case inputs, prepared request bodies, and stored response material are
excluded by default. `RawChoices(inputs=True, requests=True, responses=True)`
opts into each category independently. Included values are sanitized and keep
their original and sanitized identities. The sanitizer cannot recognize
arbitrary unknown plaintext secrets.
Saved attempts currently retain response JSON source strings, so reports do not
claim opaque response-byte evidence where the saved source has none.

JSON and Markdown render the same saved report deterministically. Partial
results remain visible, fixture evidence is labelled authored software
verification material, and saved rates retain their denominators and null
reasons. Markdown puts frozen model/compiler contexts before result identities
and keeps baseline, usage, and case evidence in a fixed order. It normalizes raw
source line endings in the rendered copy while JSON preserves the saved source.
