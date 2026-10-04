"""Installed foundation CLI; workflow commands are supplied by application owners."""

import typer

from deykit import __version__

app = typer.Typer(help="Deykit — local typed decision debugging.", no_args_is_help=True)


def show_version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", callback=show_version, is_eager=True),
) -> None:
    """Inspect the installed Deykit foundation."""
