# Author in the browser

The browser workspace is a local authoring interface for projects, decisions,
examples, provider profiles, and authored fixture sets. Open an existing project,
create a new one, or make an editable copy of the support demo. The sidebar keeps
the selected project in view while you move between its authoring pages.

Decision edits remain drafts and save automatically. You can edit the exact
definition source when the service cannot show its structured fields. Saving a
version checks the latest decision and draft ETags and keeps each saved version
immutable. Version history can inspect, compare, and explicitly restore a saved
definition to the draft. Removing an option first shows the references the service
reports; existing labels are never silently rewritten.

Datasets and cases can be authored before a decision exists. Import accepts CSV or
JSONL source text and asks the local service to parse and preview every row. Rows
with errors are excluded by default; selecting the valid-row option is an explicit
choice. Splits use a server preview, including its grouping and actual assignments,
before a new dataset revision is saved. Labels are staged against the full case,
decision, and draft review returned by the service.

Provider profiles store configuration and credential references. Secret entry is
sent only to the local credential operation and is cleared when that request
settles. Listing available models is a separate, explicit network action; ordinary
authoring does not contact a provider or submit inference requests.

Fixture sets contain authored bindings for exact cases and model identities. A
fixture does not generate an answer for a missing binding. Request source is hidden
until explicitly revealed, and the normal read omits request details.

The workspace keeps navigation state for the current local registration in memory.
Resource IDs appear in validated hash routes; source text, project paths, and
credentials do not. When a draft has unsaved editor changes, navigation asks whether
to save, discard, or keep editing. A failed save leaves the source available for
review.
