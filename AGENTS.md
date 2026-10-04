# Deykit contributor contract

Use Python 3.11+ and `uv sync --locked`. Run `uv run pytest`, `uv run ruff check .`,
`uv run mypy`, and `uv build` for relevant changes. Tests are offline: no credentials,
provider inference, or automatic network schema resolution. Preserve MIT.

Keep domain and contracts independent of HTTP, SQLite, SDKs, CLI, and UI. Application
services depend on narrow ports; adapters depend inward. User JSON crosses HTTP as
source strings and uses contracts.json_value for exact values and hashes. Never use
float or Pydantic's Decimal JSON serializer to construct user input or provider bytes.
Immutable evidence stays separate from mutable drafts and append-only run lifecycle.

Use isolated assigned worktrees; coordinate shared files and public interfaces with
their owner. Do not force-add ignored docs/ or secrets. Public engineering notes belong
in architecture/, user instructions in guide/. Distinguish authored fixture evidence,
automated verification, manual platform checks, and authorized live provider evidence.
