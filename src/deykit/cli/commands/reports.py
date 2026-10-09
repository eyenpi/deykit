"""Create, export, and inspect immutable evidence reports."""

from __future__ import annotations

from typing import Annotated, Literal, cast

import typer
from pydantic import ValidationError

from deykit.application.dataset_support import identifier
from deykit.application.errors import ServiceFailure
from deykit.application.reports import ReportService
from deykit.cli.context import CliState, SystemClock, new_operation_id, state
from deykit.cli.output import CommandOutcome, execute, execute_outcome
from deykit.cli.selection import SelectorHint, SelectorOwner, selector_hint, selection_context
from deykit.contracts.errors import ServiceError
from deykit.reports.models import (
    ExportOutcome,
    RawChoices,
    ReportFormat,
    ReportRequest,
    ReportTargetKind,
)
from deykit.storage.artifact_export import NativeArtifactWriter

app = typer.Typer(help="Save, export, and inspect immutable evidence reports.")
_TARGET_KINDS = frozenset({"run", "evaluation", "comparison", "diagnostic", "check"})


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="report")


def _invalid(reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason=reason))


def _format(value: str) -> ReportFormat:
    if value not in ("json", "markdown"):
        raise _invalid("invalid_report_format")
    return cast(ReportFormat, value)


def _kind(value: str | None) -> ReportTargetKind | None:
    if value is None:
        return None
    if value not in _TARGET_KINDS:
        raise _invalid("invalid_report_selector")
    return cast(ReportTargetKind, value)


def _human_export(outcome: ExportOutcome, mode: Literal["created", "saved"]) -> dict[str, object]:
    report = outcome.report
    return {
        "report_id": report.report_id,
        "mode": mode,
        "source": {
            "target_kind": report.target_kind,
            "target_id": report.target_id,
            "evaluation_ids": report.evaluation_ids,
            "result_snapshot_ids": report.result_snapshot_ids,
            "label_snapshot_ids": report.label_snapshot_ids,
            "comparison_id": report.comparison_id,
            "diagnostic_snapshot_id": report.diagnostic_snapshot_id,
            "check_snapshot_id": report.check_snapshot_id,
        },
        "raw": report.raw,
        "destination_status": "written" if outcome.success else "failed",
        "destination": outcome.destination if outcome.success else None,
        "artifact_hash": outcome.artifact_hash,
        "byte_count": outcome.byte_count,
    }


def _outcome(
    cli: CliState, outcome: ExportOutcome, mode: Literal["created", "saved"]
) -> CommandOutcome:
    data: object = outcome if cli.json_output else _human_export(outcome, mode)
    warnings = (outcome.durability_warning,) if outcome.durability_warning is not None else ()
    return CommandOutcome(data, warnings=warnings)


def _raise_destination_failure(cli: CliState, outcome: ExportOutcome) -> None:
    if outcome.success:
        return
    if not cli.json_output:
        error = outcome.error or ServiceError(code="internal_error", reason="export_write_failed")
        reason = f" ({error.reason})" if error.reason else ""
        typer.echo(f"Error: {error.message}{reason}", err=True)
    # Emit the complete typed outcome first, so JSON retains the saved ReportID.
    raise typer.Exit(2)


@app.command("export")
def export(
    ctx: typer.Context,
    output: Annotated[str, typer.Option("--output", "--destination", "-o")],
    target_id: Annotated[str | None, typer.Argument()] = None,
    report_id: Annotated[str | None, typer.Option("--report-id")] = None,
    format_name: Annotated[str, typer.Option("--format")] = "markdown",
    target_kind: Annotated[str | None, typer.Option("--target-kind")] = None,
    evaluation: Annotated[str | None, typer.Option("--evaluation")] = None,
    result_snapshot: Annotated[str | None, typer.Option("--result-snapshot")] = None,
    group_snapshot: Annotated[str | None, typer.Option("--group-snapshot")] = None,
    include_raw_inputs: Annotated[bool, typer.Option("--include-raw-inputs")] = False,
    include_raw_requests: Annotated[bool, typer.Option("--include-raw-requests")] = False,
    include_raw_responses: Annotated[bool, typer.Option("--include-raw-responses")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Create and export a report, or export an already saved report."""

    captured: ExportOutcome | None = None

    def work(cli: CliState) -> CommandOutcome:
        nonlocal captured
        selected_format = _format(format_name)
        raw_requested = include_raw_inputs or include_raw_requests or include_raw_responses
        creation_selector = any(
            item is not None
            for item in (target_kind, evaluation, result_snapshot, group_snapshot, operation_id)
        )

        request: ReportRequest | None
        selected_report_id: str | None
        actual_operation_id: str | None
        mode: Literal["created", "saved"]
        if report_id is not None:
            if target_id is not None or creation_selector or raw_requested:
                raise _invalid("invalid_report_selector")
            selected_report_id = identifier(report_id)
            request = None
            actual_operation_id = None
            mode = "saved"
        else:
            if target_id is None:
                raise _invalid("invalid_report_selector")
            selected_target_id = identifier(target_id)
            selected_kind = _kind(target_kind)
            try:
                request = ReportRequest(
                    target_id=selected_target_id,
                    target_kind=selected_kind,
                    evaluation_id=evaluation,
                    result_snapshot_id=result_snapshot,
                    group_snapshot_id=group_snapshot,
                    raw=RawChoices(
                        inputs=include_raw_inputs,
                        requests=include_raw_requests,
                        responses=include_raw_responses,
                    ),
                )
            except (ValidationError, ValueError):
                raise _invalid("invalid_report_request") from None
            if operation_id is not None:
                identifier(operation_id)
            # Request and format admission happen before project discovery and ID allocation.
            actual_operation_id = new_operation_id(operation_id)
            selected_report_id = None
            mode = "created"

        with cli.source() as source:
            if report_id is not None:
                hints = (selector_hint("report", report_id, ()),)
            else:
                allowed = (
                    ("run", "evaluation", "comparison")
                    if target_kind is None
                    else {
                        "run": ("run",),
                        "evaluation": ("evaluation",),
                        "comparison": ("comparison",),
                        "diagnostic": ("execution_group",),
                        "check": ("execution_group",),
                    }.get(target_kind, ())
                )
                target_hint = SelectorHint(
                    kinds=allowed,  # type: ignore[arg-type]
                    resource_id=target_id or "",
                    scopes={kind: () for kind in allowed},  # type: ignore[misc]
                )
                hints_list: list[SelectorHint] = [target_hint]
                if evaluation is not None:
                    hints_list.append(
                        selector_hint(
                            "evaluation",
                            evaluation,
                            (),
                            owner=(
                                SelectorOwner("run", target_id)
                                if target_kind == "run" and target_id is not None
                                else None
                            ),
                        )
                    )
                if result_snapshot is not None:
                    if target_kind == "run":
                        hints_list.append(
                            selector_hint(
                                "result_snapshot",
                                result_snapshot,
                                (),
                                owner=(
                                    SelectorOwner("run", target_id)
                                    if target_id is not None
                                    else None
                                ),
                            )
                        )
                    elif target_kind is None:
                        hints_list.append(
                            selector_hint("result_snapshot", result_snapshot, ())
                        )
                if group_snapshot is not None and target_kind in {"diagnostic", "check"}:
                    snapshot_kind = (
                        "diagnostic_snapshot" if target_kind == "diagnostic" else "check_snapshot"
                    )
                    hints_list.append(
                        SelectorHint(
                            (snapshot_kind,),
                            group_snapshot,
                            {snapshot_kind: ()},
                            SelectorOwner(
                                "execution_group",
                                target_id or "",
                                (
                                    "choice_order"
                                    if target_kind == "diagnostic"
                                    else "regression_check"
                                ),
                            ),
                        )
                    )
                hints = tuple(hints_list)
            with selection_context(source, hints):
                service = ReportService(source, SystemClock())
                if request is not None:
                    assert actual_operation_id is not None
                    saved = service.create(request, operation_id=actual_operation_id)
                    selected_report_id = saved.record.id
                assert selected_report_id is not None
                writer = NativeArtifactWriter((source.root,), sanitizer=service.sanitizer)
                captured = service.export(
                    selected_report_id,
                    format=selected_format,
                    destination=output,
                    writer=writer,
                )
                return _outcome(cli, captured, mode)

    execute_outcome(ctx, work)
    assert captured is not None
    _raise_destination_failure(state(ctx), captured)


@app.command("show")
def show(ctx: typer.Context, report_id: str) -> None:
    def work(cli: CliState) -> object:
        selected = identifier(report_id)
        with cli.source() as source:
            with selection_context(source, (selector_hint("report", selected, ()),)):
                return ReportService(source, SystemClock()).metadata(selected)

    execute(ctx, work)


@app.command("list")
def list_reports(
    ctx: typer.Context,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise _invalid("invalid_page_limit")
        selected_cursor = identifier(cursor) if cursor is not None else None
        with cli.source() as source:
            return ReportService(source, SystemClock()).list(cursor=selected_cursor, limit=limit)

    execute(ctx, work)
