# Evidence reports

The Python `ReportService` saves a fixed view of a run, evaluation, or
comparison. Later run resumes and edits to labels or decision drafts do not
replace saved evidence. Report creation and rendering make no provider calls.
When a selected run result has no original evaluation, the service evaluates
the saved answers against their original labels.

Create with `ReportService.create(ReportRequest(...), operation_id=...)`. Read
the complete saved report with `read(report_id)`. Use `metadata(report_id)` or
`list(cursor=..., limit=...)` for metadata only. Render as JSON or Markdown with
`render(report_id, format="json")` or `render(report_id, format="markdown")`.
To write an existing report, call `export(report_id, format=..., destination=...,
writer=...)`; a failed destination write keeps the report available for retry.

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
reasons.
