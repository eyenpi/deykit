"""Inspect frozen case evidence, annotate, and score saved answers locally."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from deykit.application.annotations import AnnotationService
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.results import ResultInspection
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.input import source_text
from deykit.cli.output import execute
from deykit.cli.selection import SelectorOwner, selection_context, selector_hint
from deykit.contracts.errors import ServiceError

results_app = typer.Typer(help="Browse immutable results and their evidence.")


def register(root: typer.Typer) -> None:
    root.add_typer(results_app, name="results")
    root.command("reevaluate")(reevaluate)


@results_app.command("list")
def list_results(
    ctx: typer.Context,
    run_id: str,
    evaluation: Annotated[str | None, typer.Option("--evaluation")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    split: Annotated[
        str | None, typer.Option("--split", help="development, calibration, or test")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            hints = (selector_hint("run", run_id, ()),) + (
                (selector_hint("evaluation", evaluation, (), owner=SelectorOwner("run", run_id)),)
                if evaluation is not None
                else ()
            )
            with selection_context(source, hints):
                return (
                    ResultInspection(source)
                    .list(
                        run_id,
                        evaluation_id=evaluation,
                        status=status,
                        split=split,  # validated by service
                        tag=tag,
                        cursor=cursor,
                        limit=limit,
                    )
                    .source()
                )

    execute(ctx, work)


@results_app.command("show")
def show_result(
    ctx: typer.Context,
    run_id: str,
    case_id: str,
    evaluation: Annotated[str | None, typer.Option("--evaluation")] = None,
    request: Annotated[bool, typer.Option("--request")] = False,
    response: Annotated[bool, typer.Option("--response")] = False,
    attempts: Annotated[bool, typer.Option("--attempts")] = False,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            hints = (
                selector_hint("run", run_id, ()),
                selector_hint("case", case_id, (), owner=SelectorOwner("run", run_id)),
            ) + (
                (selector_hint("evaluation", evaluation, (), owner=SelectorOwner("run", run_id)),)
                if evaluation is not None
                else ()
            )
            with selection_context(source, hints):
                return (
                    ResultInspection(source)
                    .show(
                        run_id,
                        case_id,
                        evaluation_id=evaluation,
                        include_request=request,
                        include_response=response,
                        include_attempts=attempts,
                    )
                    .source()
                )

    execute(ctx, work)


@results_app.command("annotate")
def annotate_result(
    ctx: typer.Context,
    run_id: str,
    case_id: str,
    note: Annotated[str | None, typer.Option("--note")] = None,
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    actual = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        if (note is None) == (file is None and not stdin):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="input_mode_conflict")
            )
        content = note if note is not None else source_text(file=file, stdin=stdin)
        with cli.source() as source:
            hints = (
                selector_hint("run", run_id, ()),
                selector_hint("case", case_id, (), owner=SelectorOwner("run", run_id)),
            )
            with selection_context(source, hints):
                saved = AnnotationService(source, SystemClock()).add(
                    run_id, case_id, content, operation_id=actual
                )
                return {
                    "operation_id": actual,
                    "annotation_id": saved.annotation.id,
                    "run_id": run_id,
                    "case_id": case_id,
                    "replayed": saved.replayed,
                }

    execute(ctx, work)


def reevaluate(
    ctx: typer.Context,
    run_id: str,
    result_snapshot: Annotated[str | None, typer.Option("--result-snapshot")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Freeze current labels and rescore saved answers with zero provider calls."""
    actual = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        with cli.source() as source:
            hints = (selector_hint("run", run_id, ()),) + (
                (
                    selector_hint(
                        "result_snapshot",
                        result_snapshot,
                        (),
                        owner=SelectorOwner("run", run_id),
                    ),
                )
                if result_snapshot is not None
                else ()
            )
            with selection_context(source, hints):
                snapshot_id = (
                    result_snapshot
                    or ResultInspection(source).list(run_id, limit=1).result_snapshot_id
                )
                saved = EvaluationService(source, SystemClock()).reevaluate_current_labels(
                    run_id, snapshot_id, operation_id=actual
                )
                return {
                    "operation_id": actual,
                    "evaluation_id": saved.record.id,
                    "run_id": run_id,
                    "result_snapshot_id": saved.record.result_snapshot_id,
                    "label_snapshot_id": saved.record.label_snapshot_id,
                    "replayed": saved.replayed,
                    "metrics": saved.metrics,
                    "dispatch_count": 0,
                }

    execute(ctx, work)
