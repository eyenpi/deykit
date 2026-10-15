# Contributing

Use Python 3.11+, uv and the locked dependencies. Start with the
[architecture](architecture/overview.md) and [development commands](guide/development.md).

Keep changes focused. Domain/contracts stay independent of HTTP, SQLite and
provider SDKs. Application services depend on narrow ports; adapters depend
inward. Preserve exact JSON source strings, immutable evidence, operation replay
and safe errors. Labels and credentials never enter model input.

Run relevant offline tests, Ruff, mypy and package checks. Run expensive local commands
sequentially with one verification process. Native CI jobs use independent hosted
machines; each runs one test worker. Full suites run on Linux and macOS;
Python 3.13 has a focused Linux compatibility job. Windows CI is disabled to
limit runner time; native Windows verification is deferred. Static checks
and artifact builds run once. Known documentation-only changes skip runtime jobs. Do not run live provider requests
as part of tests or CI. There is no frontend build or browser dependency.

Open a pull request explaining the problem, resulting behavior and actual
verification. Distinguish authored fixtures, automated checks, native platforms
and live-provider observations. Do not claim planned, interrupted or mocked
checks passed.

Never commit credentials, private projects, local reports or ignored `docs/`.
Run a redacted history scan before submitting suspected secret-related changes.
See [security reporting](SECURITY.md). Preserve the [MIT license](LICENSE).
