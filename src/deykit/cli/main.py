"""Installed command root; feature modules register without owning this file."""

import sys
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from deykit import __version__
from deykit.cli import authoring, commands, data, projects
from deykit.cli.context import CliState
from deykit.cli.output import emit_error
from deykit.contracts.errors import ServiceError


class SafeGroup(TyperGroup):
    """Keep parser failures in the same JSON error contract as service failures."""

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        supplied = tuple(args) if args is not None else tuple(sys.argv[1:])
        json_mode = "--json" in supplied and not any(
            option in supplied for option in ("--help", "--version", "--show-completion")
        )
        if not json_mode:
            return super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        try:
            return super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except typer.TyperException:
            emit_error(
                CliState(None, True),
                ServiceError(code="validation_error", reason="invalid_command"),
            )
            raise SystemExit(2) from None


app = typer.Typer(
    help="Deykit — local typed decision debugging.", no_args_is_help=True, cls=SafeGroup
)


def show_version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    project: Annotated[
        Path | None, typer.Option("--project", help="Portable project folder.")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="One versioned JSON result.")] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=show_version, is_eager=True)
    ] = False,
) -> None:
    """Choose an explicit project or discover its nearest parent marker."""
    ctx.obj = CliState(project, json_output)


projects.register(app)
authoring.register(app)
data.register(app)

# Later service owners add one narrow module with register(app) under cli/commands.
for module_info in sorted(iter_modules(commands.__path__), key=lambda item: item.name):
    if module_info.name.startswith("_"):
        continue
    module = import_module(f"deykit.cli.commands.{module_info.name}")
    module.register(app)
