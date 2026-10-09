"""Browser-free execution commands over the bounded run application service."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal, cast

import typer

from deykit.application.execution_actions import settle_execution
from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.output import CommandOutcome, execute, execute_outcome
from deykit.cli.selection import selection_context, selector_hint
from deykit.contracts.records import ExecutionSettings
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.runner.views import RunCreated, RunProgress, RunResumed
from deykit.storage import FileProjectSource

runs_app = typer.Typer(help="Inspect, cancel, and explicitly resume frozen runs.")


def register(root: typer.Typer) -> None:
    root.command("run")(run)
    root.add_typer(runs_app, name="runs")


def service(source: FileProjectSource) -> ExecutionService:
    clock = SystemClock()
    return ExecutionService(source, source, ProviderBackends(source, clock), clock)


def _created(value: RunCreated) -> None:
    action = "Replayed" if value.replayed else "Created"
    typer.echo(f"{action} {value.mode} run {value.run_id}", err=True)


def _resumed(value: RunResumed) -> None:
    action = "Replayed" if value.replayed else "Resumed"
    typer.echo(f"{action} run {value.run_id} segment {value.segment_id}", err=True)


def _progress(value: RunProgress) -> None:
    settled = sum(case.status not in {"pending", "unknown"} for case in value.cases)
    typer.echo(
        f"Run {value.run_id}: {settled}/{len(value.cases)} settled; "
        f"{value.attempts_used}/{value.attempt_limit} attempts",
        err=True,
    )


def _evaluated(source: FileProjectSource, result: RunProgress, operation_id: str) -> CommandOutcome:
    """Map shared settlement to the established CLI output shape."""
    settled = settle_execution(EvaluationService(source, SystemClock()), result, operation_id)
    data: dict[str, object] = {"operation_id": settled.operation_id, "run": settled.run}
    if settled.evaluation_error is not None:
        data["evaluation_error"] = settled.evaluation_error.safe_dict()
    elif settled.evaluation_pending:
        data["evaluation_pending"] = True
    elif settled.evaluation_id is not None:
        data.update(
            evaluation_id=settled.evaluation_id,
            evaluation_result_snapshot_id=settled.evaluation_result_snapshot_id,
            evaluation_replayed=settled.evaluation_replayed,
        )
    return CommandOutcome(data, settled.exit_code, settled.warnings)


def run(
    ctx: typer.Context,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    mode: Annotated[str, typer.Option("--mode", help="Explicit fixture or live mode.")],
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    fixture_set: Annotated[str | None, typer.Option("--fixture-set")] = None,
    revision: Annotated[str | None, typer.Option("--revision")] = None,
    split: Annotated[str, typer.Option("--split")] = "all",
    cases: Annotated[list[str] | None, typer.Option("--case")] = None,
    attempt_limit: Annotated[int, typer.Option("--attempt-limit", min=1)] = 100,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, max=64)] = 2,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1, max=600)] = 60,
    deadline_seconds: Annotated[int, typer.Option("--deadline-seconds", min=1, max=86_400)] = 600,
    rate_retries: Annotated[int, typer.Option("--rate-retries", min=0, max=1)] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Validate and freeze a decision, then execute exact selected requests within limits."""

    def work(cli: CliState) -> CommandOutcome:
        request = RunRequest(
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
        )
        with cli.source() as source:
            runner = service(source)
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
                    return CommandOutcome(runner.preview(request))
                actual = new_operation_id(operation_id)
                result = asyncio.run(
                    runner.start(
                        request, operation_id=actual, on_created=_created, on_progress=_progress
                    )
                )
                return _evaluated(source, result, actual)

    execute_outcome(ctx, work)


@runs_app.command("list")
def list_runs(
    ctx: typer.Context,
    decision: Annotated[str | None, typer.Option("--decision")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            if decision is None:
                return service(source).list(
                    decision_id=decision, status=status, cursor=cursor, limit=limit
                )
            with selection_context(source, (selector_hint("decision", decision, ()),)):
                return service(source).list(
                    decision_id=decision, status=status, cursor=cursor, limit=limit
                )

    execute(ctx, work)


@runs_app.command("show")
def show_run(ctx: typer.Context, run_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("run", run_id, ()),)):
                return service(source).show(run_id)

    execute(ctx, work)


@runs_app.command("cancel")
def cancel_run(
    ctx: typer.Context,
    run_id: str,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState) -> object:
        actual = new_operation_id(operation_id)
        with cli.source() as source:
            with selection_context(source, (selector_hint("run", run_id, ()),)):
                return {
                    "operation_id": actual,
                    "run": service(source).cancel(run_id, operation_id=actual),
                }

    execute(ctx, work)


@runs_app.command("resume")
def resume_run(
    ctx: typer.Context,
    run_id: str,
    retry_unknown: Annotated[bool, typer.Option("--retry-unknown")] = False,
    attempt_limit: Annotated[int | None, typer.Option("--attempt-limit", min=1)] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState) -> CommandOutcome:
        with cli.source() as source:
            runner = service(source)
            with selection_context(source, (selector_hint("run", run_id, ()),)):
                if dry_run:
                    return CommandOutcome(
                        runner.preview_resume(
                            run_id, retry_unknown=retry_unknown, max_attempts=attempt_limit
                        )
                    )
                actual = new_operation_id(operation_id)
                result = asyncio.run(
                    runner.resume(
                        run_id,
                        operation_id=actual,
                        retry_unknown=retry_unknown,
                        max_attempts=attempt_limit,
                        on_resumed=_resumed,
                        on_progress=_progress,
                    )
                )
                return _evaluated(source, result, actual)

    execute_outcome(ctx, work)
