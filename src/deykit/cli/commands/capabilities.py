"""Discover the installed parser without opening project or provider state."""

from __future__ import annotations

from typing import Annotated, cast

import typer
from typer.core import TyperArgument, TyperCommand, TyperGroup, TyperOption

from deykit import __version__
from deykit.application.errors import ServiceFailure
from deykit.cli.output import execute
from deykit.contracts.errors import ServiceError


def register(root: typer.Typer) -> None:
    root.command("capabilities")(capabilities)


def parameter_metadata(parameter: TyperArgument | TyperOption) -> dict[str, object]:
    value_type = parameter.type
    return {
        "name": parameter.name,
        "options": list(parameter.opts),
        "secondary_options": list(parameter.secondary_opts),
        "type": value_type.name,
        "default": parameter.default,
        "required": parameter.required,
        "multiple": bool(getattr(parameter, "multiple", False)),
        "nargs": parameter.nargs,
        "is_flag": bool(getattr(parameter, "is_flag", False)),
        "minimum": getattr(value_type, "min", None),
        "maximum": getattr(value_type, "max", None),
        "choices": list(getattr(value_type, "choices", ())),
        "hidden": bool(getattr(parameter, "hidden", False)),
    }


def command_catalog(group: TyperGroup, prefix: tuple[str, ...] = ()) -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    for name, registered in sorted(group.commands.items()):
        command = cast(TyperCommand | TyperGroup, registered)
        path = (*prefix, name)
        catalog.append(
            {
                "path": list(path),
                "kind": "group" if isinstance(command, TyperGroup) else "command",
                "summary": command.short_help or command.help or "",
            }
        )
        if isinstance(command, TyperGroup):
            catalog.extend(command_catalog(command, path))
    return catalog


def capabilities(
    ctx: typer.Context,
    command: Annotated[
        list[str] | None, typer.Argument(help="Optional command path, e.g. run or results show.")
    ] = None,
) -> None:
    """List commands, or describe one command's arguments and options; entirely local."""

    def work(_: object) -> dict[str, object]:
        root = ctx.find_root().command
        if not isinstance(root, TyperGroup):
            raise ServiceFailure(ServiceError(code="internal_error"))
        data: dict[str, object] = {
            "interface_version": 1,
            "tool_version": __version__,
            "guide": "guide/agents.md",
            "global_parameters": [
                parameter_metadata(cast(TyperArgument | TyperOption, parameter))
                for parameter in root.params
            ],
            "help_option": "--help",
            "parameter_scope": "parser; feature guides define semantic constraints",
            "exit_codes": {
                "0": "command completed; inspect data for run quality",
                "1": "internal error",
                "2": "invalid command, validation, conflict, or preflight failure",
                "3": "input or response failures; execution evidence is in data",
                "4": "incomplete execution; execution evidence is in data",
                "5": "regression expectation failures; check evidence is in data",
            },
        }
        if not command:
            data["commands"] = command_catalog(root)
            return data
        selected: TyperCommand | TyperGroup = root
        for part in command:
            if not isinstance(selected, TyperGroup) or part not in selected.commands:
                raise ServiceFailure(
                    ServiceError(code="validation_error", reason="unknown_command_path")
                )
            selected = cast(TyperCommand | TyperGroup, selected.commands[part])
        data["command"] = {
            "path": command,
            "kind": "group" if isinstance(selected, TyperGroup) else "command",
            "summary": selected.short_help or selected.help or "",
            "parameters": [
                parameter_metadata(cast(TyperArgument | TyperOption, parameter))
                for parameter in selected.params
            ],
        }
        if isinstance(selected, TyperGroup):
            data["commands"] = command_catalog(selected, tuple(command))
        return data

    execute(ctx, work)
