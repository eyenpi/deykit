# Review expected answers and split examples

Labels belong to one decision and dataset. An acceptable answer may contain one
or several option IDs. The application keeps labels separate from model input.
A disputed, stale, or incompatible expectation remains visible and is excluded
from correctness calculations by the evaluation layer.

The service API below is usable by a Python caller with an opened `ProjectSource`
and injected `Clock`; the CLI/browser adapters are delivered separately.

```python
from deykit.application.labels import LabelEdit, LabelService
from deykit.application.splits import SplitService

labels = LabelService(source, clock)
view = labels.read("decision", "dataset", "case")
# Display view.case and view.definition; keep view.review with staged controls.
result = labels.set(
    view.review,
    ("option_a", "option_b"),
    provenance="human",
    operation_id="review-save-1",
)

view = labels.read("decision", "dataset", "case")
labels.dispute(view.review, reason="Two reviewers disagree", operation_id="dispute-1")
view = labels.read("decision", "dataset", "case")
labels.resolve(view.review, ("option_b",), operation_id="resolve-1")
view = labels.read("decision", "dataset", "case")
labels.clear(view.review, operation_id="clear-1")
```

Each mutation needs a fresh operation ID. Retrying an identical request uses the
same ID and returns its original saved result, even after later edits. Reusing an
ID for different values is a conflict. Save conflicts require reloading and reviewing
the changed input or choices. Reading and staging expected answers never saves.

For a new label, choose `human`, `authored_fixture`, `model_generated`, or
`imported_unknown` explicitly. Existing provenance stays unchanged unless overridden.
Imported labels default to `imported_unknown`. Set preserves a disputed state;
resolve is the explicit decision that an expectation is applicable again.

Use `labels.list("decision", "dataset", status="stale")` to filter, and
`labels.history("decision", "dataset", "case")` to inspect changes, including
clears. A removed option ID remains in old expectations so you can correct it.
Renaming an option preserves identity. Editing any input field makes a label
stale; changing only tags or split does not. A case removed and added again starts
unlabelled even when it reuses its ID.

For an atomic batch, obtain one review per case and pass a tuple of `LabelEdit`
values to `labels.batch(edits, operation_id="batch-1")`. Every edit validates before
any writes; there is no silent partial save. The batch can contain set, clear,
dispute, and resolve actions. Duplicate targets are rejected.

```python
splits = SplitService(source, clock)
preview = splits.preview("dataset", seed=42)
print(preview.counts)  # Review actual counts before applying.
result = splits.commit(preview, operation_id="split-1")
print(result.snapshot.id)  # Immutable assignments and source identity.
```

The default is 80% development / 20% test. Supply exact numeric JSON text for
custom ratios, for example `ratios_source='{"development":0.6,"calibration":0.2,"test":0.2}'`.
Ratios must sum exactly to one. Related cases remain together through explicit
groups, identical full inputs, and derivation links. Large groups can prevent the
requested proportions; preview reports the actual result. Calibration is only
assigned when explicitly requested.

To assign manually, pass `assignments=(("case_a", "development"), ("case_b", "test"))`
to preview, including **every current case exactly once**. Cases in a connected
group must share a split. Partial scope, unknown IDs, duplicates, and conflicting
group assignments fail. Commit detects changes since preview and requires a new
preview. Applying a split creates a new dataset revision and preserves old snapshots.
