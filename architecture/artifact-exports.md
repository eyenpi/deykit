# Atomic artifact exports

`contracts.artifacts.ArtifactWriter` accepts a destination string and exact
`bytes`, then returns a strict immutable `ArtifactWriteOutcome`. A successful
outcome has a canonical destination and no error. A failed outcome has no
destination and includes a safe error. A durability warning is valid only
after replacement has committed.

`NativeArtifactWriter` requires an existing parent and never creates folders.
It rejects unsafe spelling, traversal, symlink or hardlink leaves, unsupported
roots, and protected project destinations. It keeps the destination's anchored
parent chain and project identity guards open through replacement. The project
manifest and all of `source/`, `history/`, and `.deykit/` are protected, even
when a protected child does not exist yet. Ordinary `reports/` and external
directories are valid destinations. Sanitizer and caller display checks apply
to both the requested and canonical paths before staging and again immediately
before replacement.

The atomic rename is the commitment point. A fault before rename returns failure
and preserves existing bytes. A fault after rename keeps success and the full
new bytes, with `export_durability_unverified`. POSIX directory flush is
attempted after rename. Windows has no assumed parent-directory flush, so its
successful exports carry that warning; native Windows execution remains
unverified until run on Windows.

POSIX descriptors keep writes anchored if a path is rebound, and the writer
checks parent identity immediately before rename. A same-permission process can
still move an anchored POSIX directory after that final check; this is an
explicit namespace-race limit. The writer does not claim power-loss durability.
