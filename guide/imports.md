# Preparing a dataset import

Use CSV with a header row or JSONL with one object per line. Choose explicitly which columns supply the case ID, input, expected answer, tags, group, split and metadata. Input and other columns must be separate. You can use a whole input column or map individual columns into top-level JSON fields.

CSV cells remain strings. Enable a field's JSON parsing flag only when that cell contains JSON, such as a nested context object or an exact decimal value. JSONL already supplies typed values. Splits are `development`, `calibration`, or `test`. Tags can be a single string or an explicitly decoded list of strings.

Expected answers require a selected decision. Supply exact option IDs, a list of acceptable IDs, or an explicit name-to-ID alias mapping. Empty expectations leave the case unlabelled. Imported expectations are recorded as `imported_unknown`; importing a file does not establish who authored its labels. Expected answers, tags and metadata are excluded from input.

Preview first. It reports row errors, duplicate input and conflicting IDs without saving anything. The default decision context is your current valid draft. Select a saved revision explicitly if that is the context you want. When IDs are not mapped, or a mapped ID cell is empty, preview assigns stable IDs. A missing mapped column is an error.

By default, any invalid row prevents all writes. To proceed with the valid subset, explicitly choose skip-invalid and retain the exact exclusions returned by commit. The same input under distinct IDs is kept and flagged; a repeated ID conflicts. A ten-row import with two invalid rows therefore writes zero rows by default, or eight rows when skip-invalid is chosen.

Editing the dataset, input files, selected decision draft or relevant labels after preview makes the preview stale. Preview again before committing. Repeating the same operation ID and unchanged request safely returns its original result; use a new operation ID for a different request.

Removing a case clears its current labels but keeps historical snapshots and operation evidence. Re-adding the same ID starts unlabelled. Archiving hides a dataset from the ordinary list and prevents new case/import changes until it is restored.

The service boundary supports these flows in Python. Use `dataset import-jsonl` and `dataset import-csv` for terminal imports; see [CLI authoring](cli-authoring.md).
