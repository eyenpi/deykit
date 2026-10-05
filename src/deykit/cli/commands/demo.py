"""Create the packaged authored demo through its application service."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from deykit.application.demo import DemoService
from deykit.cli.context import SystemClock, new_operation_id
from deykit.cli.output import execute
from deykit.storage import FileProjectSource


def register(root: typer.Typer) -> None:
    root.command("demo")(demo)


def demo(
    ctx: typer.Context,
    path: Path,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Create a new portable Sandbox project with authored fixture evidence."""
    actual = new_operation_id(operation_id)
    execute(
        ctx,
        lambda _: {
            "operation_id": actual,
            "info": DemoService(
                lambda project_path, create: FileProjectSource(project_path, create=create),
                SystemClock(),
            ).create(path.resolve(), operation_id=actual),
        },
    )
