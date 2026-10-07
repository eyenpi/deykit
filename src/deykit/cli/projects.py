"""Portable project setup and source maintenance commands."""

from pathlib import Path
from typing import Annotated

import typer

from deykit.cli.context import new_operation_id, projects_service
from deykit.cli.output import CommandOutcome, execute, execute_outcome

project_app = typer.Typer(help="Inspect and maintain a portable project.")


def register(root: typer.Typer) -> None:
    root.add_typer(project_app, name="project")
    root.command("init")(init_command)


@project_app.command("show")
def show(ctx: typer.Context) -> None:
    execute_outcome(
        ctx,
        lambda cli: _project_outcome(cli.require_project(), validate=False),
    )


@project_app.command("validate")
def validate(ctx: typer.Context) -> None:
    execute_outcome(
        ctx,
        lambda cli: _project_outcome(cli.require_project(), validate=True),
    )


def _project_outcome(path: Path, *, validate: bool) -> CommandOutcome:
    service = projects_service()
    info = service.validate(path) if validate else service.open(path)
    return CommandOutcome({"path": path, "info": info}, warnings=info.reference_warnings)


@project_app.command("rebuild-index")
def rebuild_index(ctx: typer.Context) -> None:
    execute(ctx, lambda cli: {"records": projects_service().rebuild_index(cli.require_project())})


def init_command(
    ctx: typer.Context,
    path: Path,
    name: Annotated[str, typer.Option("--name")] = "Untitled project",
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    actual = new_operation_id(operation_id)
    execute(
        ctx,
        lambda _: {
            "operation_id": actual,
            "path": path.resolve(),
            "info": projects_service().create(path, name, actual),
            "ignore_suggestions": (".deykit/", "reports/"),
        },
    )
