"""Author and inspect immutable fixture bindings through the public CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from deykit.application.fixtures import FixtureService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.input import source_text
from deykit.cli.output import execute
from deykit.cli.selection import selection_context, selector_hint

fixture_app = typer.Typer(help="Author and inspect exact offline fixture bindings.")


def register(root: typer.Typer) -> None:
    root.add_typer(fixture_app, name="fixture")


@fixture_app.command("create")
def create_fixture(
    ctx: typer.Context,
    fixture_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    name: Annotated[str, typer.Option("--name")],
    model: Annotated[str, typer.Option("--model")],
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    actual_operation_id = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        source_content = source_text(file=file, stdin=stdin)
        binding_lines = tuple(source_content.splitlines())
        with cli.source() as source:
            service = FixtureService(source, SystemClock())
            hints = (
                selector_hint("decision", decision, ()),
                selector_hint("dataset", dataset, ()),
            )
            with selection_context(source, hints):
                saved = service.create(
                    fixture_id,
                    decision,
                    dataset,
                    name,
                    model,
                    binding_lines,
                    operation_id=actual_operation_id,
                )
            return {
                "operation_id": actual_operation_id,
                "fixture": service.identity_summary(saved),
                "replayed": saved.replayed,
                "dispatch_count": 0,
            }

    execute(ctx, work)


@fixture_app.command("list")
def list_fixtures(
    ctx: typer.Context,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return FixtureService(source, SystemClock()).list(cursor=cursor, limit=limit)

    execute(ctx, work)


@fixture_app.command("show")
def show_fixture(
    ctx: typer.Context,
    fixture_id: str,
    request: Annotated[
        bool, typer.Option("--request", help="Include exact compiled request bodies.")
    ] = False,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("fixture", fixture_id, ()),)):
                # The service remains the authority for validation and summary content.
                return FixtureService(source, SystemClock()).read_summary(
                    fixture_id, include_requests=request
                )

    execute(ctx, work)
