"""Create the packaged authored demo through its application service."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from deykit.application.demo import DemoService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.output import execute
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


def register(root: typer.Typer) -> None:
    root.command("demo")(demo)


def demo(
    ctx: typer.Context,
    path: Path,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Create a new portable Sandbox project with authored fixture evidence."""
    actual = new_operation_id(operation_id)

    def work(_: CliState) -> dict[str, object]:
        info = DemoService(
            lambda project_path, create: FileProjectSource(project_path, create=create),
            SystemClock(),
            staging_factory=DemoStagingSource,
            destination_factory=FileDemoDestinationFactory(),
        ).create(path.absolute(), operation_id=actual)
        return {"operation_id": actual, "info": info}

    execute(
        ctx,
        work,
    )
