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
