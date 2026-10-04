# P01 verification evidence

Local environment: macOS ARM64, uv 0.12.23, managed CPython 3.11.16. Ordinary tests
have socket connections disabled and use no secrets, provider keys or inference.

| Requirement | Evidence |
| --- | --- |
| A01 semantic vs wire identity | Golden vectors H01/H02/H07/H08 plus wire criteria order test |
| A02 exact numeric/source round trip | H03–H12, 39-digit decimal under Decimal precision 2, browser source envelope, selected input, request and stored CaseRecord round trips |
| A03 strict JSON/schema | Duplicate escaped keys, invalid UTF-8/surrogates/nonfinite, malformed schema, blocked remote refs, local refs, exact integer/multipleOf/bounds |
| A04 stable option expectation IDs | Rename keeps applicability; deletion exposes missing IDs; disputed/stale/incompatible causes retained together |
| Resource boundaries | Actual accepted/rejected UTF-8 bytes, nesting, nodes, coefficient digits and explicit/effective exponents; maximum admitted source hashes/selects/persists; aggregate snapshot rejects explicitly |
| Frozen/safe records | Nested mutation rejection, draft/runnable separation, missing/unsupported version, extra/type rejection, exact request hash, unknown retry rejection |
| Portable package foundation | Wheel and sdist built and separately installed in clean spaced/non-ASCII paths; installed source codec round trip and CLI version/help with no Node on PATH |

Executed locally: pytest, Ruff lint/format, strict mypy, uv build, and
`tests/check_install.py`. The repeatable commands are in `guide/development.md`.
GitHub Actions also passed the Python 3.11/3.13 Ubuntu contract, build, wheel/sdist
installation and installed CLI checks on commit e5c28c6. The final successor commit
and independent final-commit review must still be inspected on the PR.

Limits: no provider compatibility/quality observation, browser workflow, SQLite or
recovery implementation, manual keyboard acceptance, Windows installation claim,
or complete A45 bundled UI/demo claim. These remain explicit later milestone gates.
