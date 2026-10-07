# Project reference validation

`project validate` checks the captured project graph after the storage adapter has
completed its normal strict record admission and recovery. The application
validator accepts one immutable tuple of `StoredRecord` values. It does not own a
source, path, clock, execution lock, provider, or credential capability.

The validator first sorts and decodes every record, rejects duplicate keys, and
checks key, scope, and canonical label identity. It then resolves every declared
hard reference in stable collection, scope, record, and field order. Only after
those references pass does it call the existing frozen-evidence admissions for
runs, snapshots, evaluations, comparisons, groups, regressions, and reports.
This makes a missing link fail before a readable legacy limitation can become a
warning. Warnings are returned only if the entire captured graph passes.

Historical records remain bound to their own snapshots. Current case edits,
removals, re-additions, label applicability, archived parents, and current
provider availability do not replace or invalidate frozen evidence. Dataset
mutation revision IDs are opaque. A label left in the current label collection
must still point to a current case; label history and frozen labels retain their
original case identity after removal.

Recognized incomplete runs and regressions can produce explicit
`legacy_run_not_executable` or `legacy_regression_not_executable` warnings when
their defined hashes and original references are valid. A report whose content
uses an older opaque profile can produce `unsupported_report_profile` after all
declared record links resolve. Unknown versions of known typed evidence, invalid
known hashes, and modern children attached to incomplete legacy evidence remain
errors. No missing field is filled from current mutable state.

`ProjectService.validate_opened(source)` probes execution activity before taking
the consistent source read, captures once, and derives both graph results and
`ProjectInfo` from that tuple. It leaves the caller-owned source open on success
and failure. `ProjectService.validate(path)` opens through the configured
factory, delegates to that method, and closes its source in `finally`. Ordinary
`open` and `project show` remain metadata-only.
