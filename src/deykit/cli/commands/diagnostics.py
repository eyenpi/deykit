"""Bounded order diagnostics using the shared runner, with explicit group recovery."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal, cast

import typer

from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService, DiagnosticView
from deykit.cli.commands.execution import service
from deykit.cli.context import CliState, new_operation_id
from deykit.cli.output import CommandOutcome, execute, execute_outcome
from deykit.cli.selection import selector_hint, selection_context
from deykit.contracts.records import ExecutionSettings
from deykit.runner.planner import RunRequest

app = typer.Typer(help="Bounded exploratory diagnostics; expanded calls share one lifetime cap.")


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="diagnose")


def _outcome(result: DiagnosticView) -> CommandOutcome:
    return CommandOutcome(
        {"group": result.group, "summary": result.summary.source() if result.summary else None},
        result.group.exit_code,
    )


@app.command("choice-order")
def choice_order(
    ctx: typer.Context,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    mode: Annotated[str, typer.Option("--mode")],
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    fixture_set: Annotated[str | None, typer.Option("--fixture-set")] = None,
    revision: Annotated[str | None, typer.Option("--revision")] = None,
    split: Annotated[str, typer.Option("--split")] = "all",
    cases: Annotated[list[str] | None, typer.Option("--case")] = None,
    orders: Annotated[int, typer.Option("--orders", min=1, max=4)] = 4,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    attempt_limit: Annotated[int, typer.Option("--attempt-limit", min=1)] = 100,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, max=64)] = 2,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1, max=600)] = 60,
    deadline_seconds: Annotated[int, typer.Option("--deadline-seconds", min=1, max=86_400)] = 600,
    rate_retries: Annotated[int, typer.Option("--rate-retries", min=0, max=1)] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Run the original order and up to three distinct seeded alternatives."""

    def work(cli: CliState) -> CommandOutcome:
        request = ChoiceOrderRequest(
            run=RunRequest(
                decision_id=decision,
                dataset_id=dataset,
                mode=cast(Literal["fixture", "live"], mode),
                provider_id=provider,
                fixture_set_id=fixture_set,
                revision_id=revision,
                split=cast(Literal["all", "development", "calibration", "test"], split),
                case_ids=tuple(cases or ()),
                settings=ExecutionSettings(
                    max_attempts=attempt_limit,
                    concurrency=concurrency,
                    timeout_seconds=timeout_seconds,
                    deadline_seconds=deadline_seconds,
                    max_retries_per_case=rate_retries,
                ),
            ),
            orders=orders,
            seed=seed,
        )
        with cli.source() as source:
            diagnostic = DiagnosticService(service(source))
            hints = [
                selector_hint("decision", decision, ()),
                selector_hint("dataset", dataset, ()),
            ]
            if provider is not None:
                hints.append(selector_hint("provider", provider, ()))
            if fixture_set is not None:
                hints.append(selector_hint("fixture", fixture_set, ()))
            if revision is not None:
                hints.append(selector_hint("revision", revision, (decision,)))
            hints.extend(selector_hint("case", case_id, (dataset,)) for case_id in (cases or ()))
            with selection_context(source, tuple(hints)):
                if dry_run:
                    return CommandOutcome(diagnostic.preview(request))
                result = asyncio.run(
                    diagnostic.start(request, operation_id=new_operation_id(operation_id))
                )
                return _outcome(result)

    execute_outcome(ctx, work)


@app.command("show")
def show(ctx: typer.Context, group_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(
                source, (selector_hint("execution_group", group_id, ()),)
            ):
                return _outcome(DiagnosticService(service(source)).read(group_id)).data

    execute(ctx, work)


@app.command("resume")
def resume(
    ctx: typer.Context,
    group_id: str,
    retry_unknown: Annotated[bool, typer.Option("--retry-unknown")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Resume a frozen diagnostic group without resetting its shared attempt cap."""

    def work(cli: CliState) -> CommandOutcome:
        with cli.source() as source:
            with selection_context(
                source, (selector_hint("execution_group", group_id, ()),)
            ):
                return _outcome(
                    asyncio.run(
                        DiagnosticService(service(source)).resume(
                            group_id,
                            operation_id=new_operation_id(operation_id),
                            retry_unknown=retry_unknown,
                        )
                    )
                )

    execute_outcome(ctx, work)
