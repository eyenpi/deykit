# Deykit

Deykit is a local decision debugger for reviewing how typed decisions behave on
examples. Author decisions, datasets, and labels; run exact authored fixtures or
explicitly selected live-provider work; then inspect frozen results and
comparisons. Diagnostics explore request-order sensitivity, while regression
checks replay saved, human-reviewed examples. JSON and Markdown reports preserve
the selected evidence and can omit raw inputs, requests, and responses.

## Try the local demo

Use Python 3.11 or newer and install the locked development environment:

```sh
uv sync --locked
uv run deykit demo ./deykit-demo
uv run deykit --project ./deykit-demo serve --no-open
```

The demo creates a portable project from authored fixture content. It needs no
provider key and does not measure model quality. Open the local workspace shown
by the service, or follow the [CLI walkthrough](guide/cli-workflow.md). The
browser and CLI both work with local project data; see [local API usage](guide/local-api.md).

## Explore

Start with [browser authoring](guide/browser-authoring.md) to edit decisions,
examples, fixture sets, and labels. [Execution review](guide/browser-execution.md)
covers previewing and starting bounded runs, inspecting frozen evaluations, and
explicitly selecting live-provider execution when appropriate. Use
[debugging and regression review](guide/browser-debugging.md) to filter saved
results, compare evaluations, annotate cases, and create regression examples
with explicitly selected acceptable answers. Diagnostic and check groups have
shared request limits and keep selected snapshots immutable as newer progress
arrives. Reports are saved artifacts, not new executions.

For contributor checks, see [development and verification](guide/development.md).
The architecture notes record the scope and limits of [browser execution](architecture/browser-execution-verification.md),
[browser debugging](architecture/browser-debugging-verification.md), and
[reports](architecture/reports.md). Authored fixtures verify software behavior;
live-provider observations, CI, native platforms and physical accessibility or
IME checks remain separate evidence. Licensed under [MIT](LICENSE).
