# Architecture

Deykit is a terminal-first local application with a CLI and an optional headless
HTTP adapter. There is no frontend or bundled UI. Projects are portable readable
source and history files. SQLite is a rebuildable index, not authoritative evidence.

| Layer | Responsibility |
| --- | --- |
| `contracts/`, `domain/` | Exact JSON, versioned records, identities, pure validation and ports |
| `application/` | Authoring, labels, imports, reviewed execution and evidence services |
| `runner/`, evaluations, comparisons, diagnostics and regressions | Bounded execution, frozen evidence and analysis |
| `storage/`, `providers/` | Journaled filesystem/index and explicit provider adapters |
| `cli/`, `api/` | Terminal presentation, transport admission and composition |

User JSON crosses HTTP as source strings and uses the shared exact codec for
values and hashes. Labels are outside provider input. Evidence is immutable;
drafts are mutable and lifecycle records append. Unknown attempts never retry
automatically, resume preserves lifetime limits, and opening or inspecting a
project performs no inference. Fixture evidence is authored software evidence.

See the [contracts](contracts.md), [storage](storage.md),
[runner](runner.md) and [verification status](verification.md).
