# Deykit

Deykit is a local tool that AI agents can use to test and debug typed AI
decisions: classification, routing, structured JSON answers, prompt versions and
regression checks. Give your agent this repository and a task; it can use the CLI
directly from the checkout and return inspectable evidence.

## Give this repo to your agent

Ask your agent to read [AGENTS.md](AGENTS.md) and the
[agent workflow guide](guide/agents.md), then work on your examples in a separate
local project. A useful starting request is:

> Use Deykit to evaluate this decision on my examples. Start offline, preserve
> exact inputs, show failures and exclusions, and export a report. Ask for live
> execution only if my request has not already authorized the provider and limits.

The instructions are self-contained and require no private services. The CLI
returns versioned JSON, exposes its current command parameters, previews work,
and preserves immutable results and retry receipts.

## Start from a checkout

Requires Python 3.11+ and uv. Clone this repo or use an existing checkout:

```sh
git clone https://github.com/eyenpi/deykit.git
cd deykit
uv sync --locked
uv run deykit --json capabilities
uv run deykit --json capabilities run
uv run python guide/examples/agent-quickstart.py --output /absolute/new/deykit-example
```

Choose a new output directory. The quickstart discovers the CLI, creates a demo,
previews and executes one fixture case, verifies safe replay, checks a missing
selector, and exports a report with structured command receipts. It needs no key
and makes no provider requests. Fixture outcomes are authored software evidence;
they do not measure model quality.

For commands launched from another working directory, pin both locations:

```sh
uv run --directory /absolute/deykit -- deykit \
  --project /absolute/your-project --json project validate
```

The [full offline walkthrough](guide/cli-workflow.md) covers authoring exact JSON,
labels, comparisons, reevaluation, diagnostics and frozen regression checks:

```sh
uv run python guide/examples/cli-workflow.py --output /absolute/new/walkthrough
```

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
