"""Zero-call regression authoring and explicitly bounded frozen checks."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal, cast

import typer

from deykit.application.checks import CheckRequest, CheckService
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.cli.commands.execution import service
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.output import CommandOutcome, execute, execute_outcome
from deykit.contracts.records import ExecutionSettings

regressions_app = typer.Typer(help="Save immutable input and explicit expected-option regressions.")
checks_app = typer.Typer(help="Inspect or explicitly resume frozen regression checks.")


def register(root: typer.Typer) -> None:
    root.add_typer(regressions_app, name="regression")
    root.add_typer(checks_app, name="checks")
    root.command("check")(check)


@regressions_app.command("add")
def add(
    ctx: typer.Context,
    run_id: str,
    case_id: str,
    expected: Annotated[list[str], typer.Option("--expected")],
    reason: Annotated[str, typer.Option("--reason")],
    result_snapshot: Annotated[str | None, typer.Option("--result-snapshot")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
    provenance: Annotated[str, typer.Option("--provenance")] = "human",
) -> None:
    """Freeze an exact saved input and acceptable IDs, without provider calls."""

    def work(cli: CliState) -> object:
        with cli.source() as source:
            return RegressionService(source, SystemClock()).add(
                RegressionAdd(
                    run_id=run_id,
                    case_id=case_id,
                    acceptable_option_ids=tuple(expected),
                    reason=reason,
                    result_snapshot_id=result_snapshot,
                    provenance=cast(
                        Literal["human", "authored_fixture", "imported_unknown", "model_generated"],
                        provenance,
                    ),
                ),
                operation_id=new_operation_id(operation_id),
            )

    execute(ctx, work)


@regressions_app.command("list")
def list_regressions(
    ctx: typer.Context, decision: Annotated[str, typer.Option("--decision")]
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return RegressionService(source, SystemClock()).list(decision)

    execute(ctx, work)


@regressions_app.command("remove")
def remove(
    ctx: typer.Context,
    regression_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Remove current visibility while preserving old checks and immutable evidence."""

    def work(cli: CliState) -> object:
        with cli.source() as source:
            return RegressionService(source, SystemClock()).remove(
                regression_id, decision_id=decision, operation_id=new_operation_id(operation_id)
            )

    execute(ctx, work)


def check(
    ctx: typer.Context,
    decision: Annotated[str, typer.Option("--decision")],
    mode: Annotated[str, typer.Option("--mode")],
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    fixture_set: Annotated[str | None, typer.Option("--fixture-set")] = None,
    revision: Annotated[str | None, typer.Option("--revision")] = None,
    regressions: Annotated[list[str] | None, typer.Option("--regression")] = None,
    attempt_limit: Annotated[int, typer.Option("--attempt-limit", min=1)] = 100,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, max=64)] = 2,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1, max=600)] = 60,
    deadline_seconds: Annotated[int, typer.Option("--deadline-seconds", min=1, max=86_400)] = 600,
    rate_retries: Annotated[int, typer.Option("--rate-retries", min=0, max=1)] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Execute frozen regressions; unmet expectations exit 5 after run errors are considered."""

    def work(cli: CliState) -> CommandOutcome:
        request = CheckRequest(
            decision_id=decision,
            mode=cast(Literal["fixture", "live"], mode),
            provider_id=provider,
            fixture_set_id=fixture_set,
            revision_id=revision,
            regression_ids=tuple(regressions or ()),
            settings=ExecutionSettings(
                max_attempts=attempt_limit,
                concurrency=concurrency,
                timeout_seconds=timeout_seconds,
                deadline_seconds=deadline_seconds,
                max_retries_per_case=rate_retries,
            ),
        )
        with cli.source() as source:
            checks = CheckService(service(source))
            if dry_run:
                return CommandOutcome(checks.preview(request))
            result = asyncio.run(checks.start(request, operation_id=new_operation_id(operation_id)))
            return CommandOutcome(result, result.exit_code)

    execute_outcome(ctx, work)


@checks_app.command("show")
def show(ctx: typer.Context, group_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return CheckService(service(source)).read(group_id)

    execute(ctx, work)


@checks_app.command("resume")
def resume(
    ctx: typer.Context,
    group_id: str,
    retry_unknown: Annotated[bool, typer.Option("--retry-unknown")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState) -> CommandOutcome:
        with cli.source() as source:
            result = asyncio.run(
                CheckService(service(source)).resume(
                    group_id,
                    operation_id=new_operation_id(operation_id),
                    retry_unknown=retry_unknown,
                )
            )
            return CommandOutcome(result, result.exit_code)

    execute_outcome(ctx, work)
