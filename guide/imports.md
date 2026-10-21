# Preparing a dataset import

Use CSV with a header row or JSONL with one object per line. Choose explicitly which columns supply the case ID, input, expected answer, tags, group, split and metadata. Input and other columns must be separate. You can use a whole input column or map individual columns into top-level JSON fields.

CSV cells remain strings. Enable a field's JSON parsing flag only when that cell contains JSON, such as a nested context object or an exact decimal value. JSONL already supplies typed values. Splits are `development`, `calibration`, or `test`. Tags can be a single string or an explicitly decoded list of strings.

Expected answers require a selected decision. Supply exact option IDs, a list of acceptable IDs, or an explicit name-to-ID alias mapping. Empty expectations leave the case unlabelled. Imported expectations are recorded as `imported_unknown`; importing a file does not establish who authored its labels. Expected answers, tags and metadata are excluded from input.

Preview first. It reports row errors, duplicate input and conflicting IDs without saving anything. The default decision context is your current valid draft. Select a saved revision explicitly if that is the context you want. When IDs are not mapped, or a mapped ID cell is empty, preview assigns stable IDs. A missing mapped column is an error.

By default, any invalid row prevents all writes. To proceed with the valid subset, explicitly choose skip-invalid and retain the exact exclusions returned by commit. The same input under distinct IDs is kept and flagged; a repeated ID conflicts. A ten-row import with two invalid rows therefore writes zero rows by default, or eight rows when skip-invalid is chosen.

Editing the dataset, input files, selected decision draft or relevant labels after preview makes the preview stale. Preview again before committing. Repeating the same operation ID and unchanged request safely returns its original result; use a new operation ID for a different request.

Removing a case clears its current labels but keeps historical snapshots and operation evidence. Re-adding the same ID starts unlabelled. Archiving hides a dataset from the ordinary list and prevents new case/import changes until it is restored.

Use `dataset import --format jsonl` or `dataset import --format csv` for terminal
imports; see [CLI authoring](cli-authoring.md).

## Managed local images

Add an `images` array to the import mapping. Each entry selects a separate local
path column and gives the image a stable name. Image columns cannot overlap input,
expectation or metadata columns. Paths use `/` separators and are relative to an
explicit absolute `--asset-root`; URLs, traversal, links and special files are
rejected. The HTTP import endpoint does not read local image paths.

For a JSONL row such as
`{"id":"product-1","text":"Red bottle","photo":"product.png","expected":"red"}`:

```json
{
  "schema_version": 1,
  "input_kind": "json",
  "fields": [{"source": "text", "target": "text"}],
  "id_column": "id",
  "expected_column": "expected",
  "images": [{
    "source": "photo",
    "name": "product",
    "preparation": {"mode": "pad", "min_width": 256, "min_height": 256,
                    "background": [255, 255, 255]}
  }]
}
```

```sh
uv run deykit --project /absolute/project --json dataset import products \
  --file /absolute/products.jsonl --format jsonl --mapping /absolute/mapping.json \
  --decision category --asset-root /absolute/photos --dry-run > /absolute/preview.json
uv run deykit --project /absolute/project --json dataset import products \
  --preview /absolute/preview.json --asset-root /absolute/photos \
  --operation-id import-products-images
```

Preview performs local decoding and shows each row's source/prepared hash, byte
count, dimensions, format and preparation settings, without saving assets or
calling a provider. Commit reopens the same files and repeats preparation; changed
or missing files invalidate the reviewed preview. A completed operation replay
uses its saved receipt. Private paths remain in your input/preview files; project
asset records contain bytes and identities, without the original filesystem path.

Omit `preparation` or use `{"mode":"preserve"}` to keep the exact original bytes.
`pad` adds an RGB canvas up to the requested minimum dimensions without scaling or
cropping. The source is centered with extra odd pixels on the right/bottom. When
padding is needed, `center-pad-rgb-v1` writes a PNG with compression level zero and
no copied ancillary metadata. It requires RGB pixels with no EXIF orientation
transform. Already large enough images retain their original bytes. There is no
automatic orientation correction, color conversion, resizing or recompression.

Supported sources are single-frame PNG, JPEG and WebP. Each source and prepared
image is limited to 4 MiB, 8,192 pixels per dimension and 16 million pixels.
Unsupported images and preparations are row errors; skip-invalid remains explicit.
An import also has a 64 MiB aggregate limit for unique base64 source/prepared
image material encountered during preparation. Shared asset IDs count once.
Preview and commit enforce this limit incrementally and fail the entire import
with `import_image_resource_limit` before writing anything. Split a larger import
into separately reviewed batches. Asset admission uses a cache bounded by 64 MiB
of serialized record bytes within each captured view; it never reuses validation
across changed views.

The project stores immutable `source/image_assets/image-<hash>.json` records with
base64 source/prepared bytes. Cases and frozen run snapshots reference their IDs.
Copy the complete project to preserve those dependencies. Inspection, planning,
resume and report creation detect missing or changed referenced assets. Labels
bind to text/JSON plus named original image hashes; a preprocessing-only change
keeps expectations applicable, while changing an original image makes them stale.

Comparisons require both frozen runs to use the **same dataset ID**. After saving
the first run, prepare a variant by importing its images into a staging dataset
with explicit preparation settings. Then update the original cases' `images`
references using `case edit`, preserving their text/JSON source, tags, split,
group, derivation and metadata. Existing labels remain attached to the original
cases. For example, export `case show product-1 --dataset products` and
`case show product-1 --dataset prepared-assets` as JSON into `original.json` and
`prepared.json`, then construct the case edit document:

```python
import json
from pathlib import Path

original = json.loads(Path("original.json").read_text())["data"]["record"]
prepared = json.loads(Path("prepared.json").read_text())["data"]["record"]
assert {i["name"]: i["source_hash"] for i in original["images"]} == {
    i["name"]: i["source_hash"] for i in prepared["images"]
}
fields = (
    "input_kind",
    "input_source",
    "tags",
    "split",
    "group_id",
    "derived_from",
    "metadata_source",
)
edit = {name: original[name] for name in fields}
edit["images"] = prepared["images"]
Path("case-edit.json").write_text(json.dumps(edit))
```

This copies user JSON **source strings** unchanged. Apply the edit with explicit
preconditions from the case and dataset views you inspected:

```sh
uv run deykit --project /absolute/project --json case edit product-1 \
  --dataset products --file /absolute/case-edit.json \
  --if-hash CASE_ETAG --if-dataset-hash DATASET_ETAG --operation-id use-prepared-image
```

Run the second variant against `products` and compare the two frozen evaluations.
Changed selected image treatments appear in `changed_input` exclusions while both
runs retain their original snapshots. Preserve both import previews and asset
dependencies. Decisions select images separately using `selected_images`, for example
`"selected_images":["product"]`; only those images reach an image-capable compiler.
The existing Jev text/fixture compiler rejects selected images before dispatch.
Provider image wire formats are separate follow-ups (#58/#59). Text-only decisions
can use an image-bearing dataset while leaving `selected_images` empty.
