# Decision authoring service

`DecisionService` owns authoring state transitions over `ProjectSource`. It has no
filesystem, HTTP, SQLite, provider, CLI, or UI dependency. A caller supplies the
project source, a clock, and a revision ID factory. The source is authoritative;
the service never keeps a mutable cache.

| State | Resource key | Write behavior |
| --- | --- | --- |
| Decision pointer | `decisions/<decision-id>` | Name, archive flag, latest revision ID; replace with expected ETag |
| Draft | `drafts/<decision-id>` | Exact editor source, even if incomplete; replace with expected ETag |
| Revision | `revisions/<decision-id>/<revision-id>` | Validated definition, semantic hash, note and time; create once |

Create atomically writes pointer and draft. Save validates the entire draft, then
atomically creates a revision and replaces the pointer and draft base revision.
Historical revision bodies are never edited. Name/archive changes replace only the
pointer, so they do not change the definition hash. Restoring an old revision copies
its validated definition into the current draft; the old revision remains immutable.

Mutations require an operation ID. Their application-intent hash includes the command,
resource IDs, requested values and expected ETags. It excludes generated timestamps
and revision IDs. `operation_receipt` recovers the original committed result after a
retry, even after a later edit, and rejects reusing the ID for a changed request.
`ProjectSource.commit` checks ETags and commits all changes as one durable operation.
Callers must retain the ETags returned by reads and report `conflict` on stale writes.

Only `ChoiceDefinition` can be saved or used to select model input. Draft validation
uses the exact JSON parser and local-only Draft 2020-12 schema compiler. It validates
the full case input before selecting fields. The selected `JsonDocument` retains exact
numbers and omits labels, metadata, and unselected fields. Option/question IDs stay
stable across display-name edits. A diff reports removed IDs and references in
current labels and regressions that became incompatible; it never rewrites either
historical record.

Draft update and revision-to-draft restore hold the source boundary from the
archive-state read through commit. A simultaneous archive therefore waits or reports
`source_busy`; an edit cannot pass an unarchived check and commit after an archive.
Save checks both decision and draft ETags in its atomic commit. Definition diffs
include option-order changes even when the option set and texts are unchanged.

Reads use `consistent_read` to recover pending source journals and avoid mixed
source boundaries. Persisted records are decoded with `load_record`, rejecting
unsupported versions and malformed content before any dependent mutation. Pagination
uses ascending resource ID order, exclusive cursors and a 1–500 item limit.

Automated tests use authored definitions and inputs. They prove service behavior,
not model quality or provider compatibility. No live inference or manual browser
acceptance is claimed here.
