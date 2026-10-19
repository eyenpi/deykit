# Deykit

Deykit is a local tool that AI agents can use to test and debug typed AI
decisions: classification, routing, structured JSON answers, prompt versions and
regression checks. Give your agent this repository and a task; it can use the CLI
directly from the checkout and return inspectable evidence.

## Give this repo to your agent

Ask your agent to read [AGENTS.md](AGENTS.md) and the
[agent workflow guide](guide/agents.md), then work on your examples in a separate
local project. A useful starting request is:

> Use https://github.com/eyenpi/deykit to evaluate this decision on my examples. Start offline, preserve
> exact inputs, show failures and exclusions, and export a report. Ask for live
> execution only if my request has not already authorized the provider and limits.

The instructions are self-contained and require no private services. The CLI
returns versioned JSON, exposes its current command parameters, previews work,
and preserves immutable results and retry receipts.

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
