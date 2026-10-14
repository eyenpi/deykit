# Deykit

Deykit is a terminal tool for debugging typed decisions on examples. Author
choices or JSON decisions, datasets and reviewed labels; execute authored fixtures
or explicitly selected live-provider work; inspect frozen results, compare
versions, diagnose request-order sensitivity and replay regression checks.
JSON and Markdown reports preserve selected evidence with optional raw content.

## Try it

Requires Python 3.11+ and uv:

```sh
uv sync --locked
uv run deykit --json demo ./deykit-demo
uv run deykit --project ./deykit-demo --json project validate
uv run deykit --help
```

The demo creates a portable project with 12 cases, 11 authored fixture bindings
and 9 labels. It makes no provider requests and does not measure model quality.
Use the IDs returned by commands rather than copying placeholder IDs.
There is no browser UI or Node requirement.

For a complete offline walkthrough, run:

```sh
uv run python guide/examples/cli-workflow.py --output './walkthrough output'
```

The output directory must be new. The [walkthrough](guide/cli-workflow.md) covers exact JSON, runs, results,
reports, reevaluation, comparisons, diagnostics and regression checks.

## Workflows

- [CLI reference](guide/cli-reference.md) and [authoring](guide/cli-authoring.md)
- [Providers and credentials](guide/providers.md), [execution](guide/runs.md)
- [Comparisons](guide/comparisons.md), [diagnostics and regressions](guide/diagnostics-regressions.md)
- [Reports](guide/reports.md) and [portable projects](guide/project.md)

Projects and evidence remain local. Commands open project files directly; no
server is required. The optional [headless API](guide/local-api.md) is retained
for integrations and serves no pages. Live execution is explicit and may cost
money; tests and the authored walkthrough stay offline.

See [Contributing](CONTRIBUTING.md), [development](guide/development.md),
[architecture](architecture/overview.md), [verification status](architecture/verification.md),
[security](SECURITY.md) and the [public repository checklist](guide/public-repository.md).
This is an early local tool. Licensed under [MIT](LICENSE).
