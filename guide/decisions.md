# Author a decision

A decision asks one choice question. Give it instructions and at least two options,
each with a stable ID and a display name. Choose text or JSON input. For JSON input,
you may declare a local Draft 2020-12 schema and select the fields shown to the
model. The whole input must satisfy the schema before selection.

Drafts keep editor text even while it is incomplete. Saving a version requires a
valid definition. A saved version is immutable; each later save creates another
revision. A run can use a saved revision while you continue editing the draft.

Keep IDs when renaming a question or option. If you remove an option, labels or
regression expectations that refer to its ID become incompatible and remain visible
for review. Renaming the decision or archiving it leaves saved versions and their
hashes intact. Restoring a saved version to the draft copies its content so you can
edit it without changing history.

If another editor has changed the draft or decision pointer since you read it, reload
the latest state and reconcile your changes. Every edit uses the ETag from its read;
a stale ETag produces a conflict instead of overwriting the newer source.
