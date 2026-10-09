"""Create the packaged authored demo through its application service."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from deykit.application.demo import DemoInfo, DemoService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.output import execute
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource


def register(root: typer.Typer) -> None:
    root.command("demo")(demo)


def demo(
    ctx: typer.Context,
    path: Path,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
    open_browser: Annotated[bool, typer.Option("--open")] = False,
) -> None:
    """Create a new portable Sandbox project with authored fixture evidence."""
    actual = new_operation_id(operation_id)
    created: list[DemoInfo] = []

    def work(_: CliState) -> dict[str, object]:
        info = DemoService(
            lambda project_path, create: FileProjectSource(project_path, create=create),
            SystemClock(),
            staging_factory=DemoStagingSource,
        ).create(path.resolve(), operation_id=actual)
        created.append(info)
        return {"operation_id": actual, "info": info}

    execute(
        ctx,
        work,
    )
    if open_browser:
        from deykit.cli.commands.serve import launch_local_server

        launch_local_server(created[0].path, open_browser=True)
