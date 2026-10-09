"""The published command matrix covers every registered CLI leaf exactly once."""

import ast
import json
from pathlib import Path

from typer.core import TyperGroup
from typer.main import get_command
from typer.testing import CliRunner

from deykit.cli.main import app


def _leaves(group: TyperGroup, prefix: tuple[str, ...] = ()) -> set[str]:
    paths: set[str] = set()
    for name, command in group.commands.items():
        path = (*prefix, name)
        if isinstance(command, TyperGroup):
            paths.update(_leaves(command, path))
        else:
            paths.add(" ".join(path))
    return paths


def _groups(group: TyperGroup, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = {prefix}
    for name, command in group.commands.items():
        if isinstance(command, TyperGroup):
            paths.update(_groups(command, (*prefix, name)))
    return paths


def _command(group: TyperGroup, path: tuple[str, ...]):
    selected = group
    for name in path:
        selected = selected.commands[name]
    return selected


def _parameter_metadata(parameter) -> dict[str, object]:
    value_type = parameter.type
    options = getattr(parameter, "opts", None)
    if options is None:
        options = (parameter.name,)
    return {
        "name": parameter.name,
        "options": list(options),
        "secondary_options": list(getattr(parameter, "secondary_opts", ())),
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


def _has_qualified_symbol(tree: ast.AST, symbol: str) -> bool:
    parts = symbol.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        return False
    scope = [tree]
    for part in parts:
        matches = []
        for parent in scope:
            body = getattr(parent, "body", ())
            matches.extend(
                item
                for item in body
                if isinstance(
                    item,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                )
                and item.name == part
            )
        if not matches:
            return False
        scope = matches
    return True


def test_matrix_implemented_rows_match_registered_cli_leaves() -> None:
    matrix_path = Path(__file__).parents[2] / "architecture" / "cli-command-matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = matrix["commands"]
    paths = [row["path"] for row in rows]
    assert len(paths) == len(set(paths))
    implemented = {row["path"] for row in rows if row["status"] == "implemented"}
    command_root = get_command(app)
    command_leaves = _leaves(command_root)
    implemented_leaves = implemented & command_leaves
    variants = implemented - command_leaves
    assert implemented_leaves == command_leaves
    for row in rows:
        assert row["status"] in {"implemented", "planned"}
        assert set(row["verification"]) == {"registration", "behavior"}
        if row["status"] == "planned":
            assert row["verification"] == {"registration": "pending", "behavior": "pending"}
            continue
        for reference in row["verification"].values():
            assert reference.startswith(("tests/", "src/")), reference
            relative_path, separator, symbol = reference.partition("::")
            assert separator and symbol, reference
            assert not symbol.endswith("."), reference
            assert relative_path.endswith(".py"), reference
            assert ".." not in Path(relative_path).parts, reference
            target = matrix_path.parents[1] / relative_path
            assert target.is_file(), reference
            tree = ast.parse(target.read_text(encoding="utf-8"), filename=reference)
            assert _has_qualified_symbol(tree, symbol), reference

    runner = CliRunner()
    for path in sorted(_groups(command_root)):
        result = runner.invoke(app, [*path, "--help"] if path else ["--help"])
        assert result.exit_code == 0, " ".join(path)
        assert "Usage:" in result.output, " ".join(path)
    for path in sorted(implemented_leaves):
        result = runner.invoke(app, [*path.split(), "--help"])
        assert result.exit_code == 0, path
        assert "Usage:" in result.output, path
    for path in sorted(variants):
        parts = path.split()
        command_path = " ".join(part for part in parts if not part.startswith("-"))
        flags = [part for part in parts if part.startswith("-")]
        assert command_path in command_leaves, path
        assert flags, path
        result = runner.invoke(app, [*command_path.split(), "--help"])
        assert result.exit_code == 0, command_path
        for flag in flags:
            assert flag in result.output, (path, flag)


def test_documented_cli_parameter_inventory_matches_typer_metadata() -> None:
    inventory_path = Path(__file__).parents[2] / "architecture" / "cli-parameter-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    root = get_command(app)
    assert isinstance(root, TyperGroup)
    matrix_rows = json.loads(
        (inventory_path.parent / "cli-command-matrix.json").read_text(encoding="utf-8")
    )["commands"]
    command_leaves = _leaves(root)
    implemented = {
        row["path"]
        for row in matrix_rows
        if row["status"] == "implemented" and row["path"] in command_leaves
    }
    assert set(inventory["commands"]) == implemented
    for row in matrix_rows:
        if row["status"] != "implemented" or row["path"] in command_leaves:
            continue
        command_path = " ".join(part for part in row["path"].split() if not part.startswith("-"))
        assert command_path in inventory["commands"], row["path"]

    for path, command_contract in inventory["commands"].items():
        command = _command(root, tuple(path.split()))
        actual_parameters = [_parameter_metadata(parameter) for parameter in command.params]
        assert actual_parameters == command_contract["parameters"], path
        assert Path(command_contract["guide"]).is_file(), (path, command_contract["guide"])

    for semantic in inventory["semantic_values"]:
        guide = Path(semantic["guide"])
        text = guide.read_text(encoding="utf-8")
        for value in semantic["accepted_values"]:
            assert value in text, (semantic["command"], semantic["parameter"], value)

    runner = CliRunner()
    for path, command_contract in inventory["commands"].items():
        help_result = runner.invoke(app, [*path.split(), "--help"])
        assert help_result.exit_code == 0, help_result.output
        command = _command(root, tuple(path.split()))
        for _, expected in zip(command.params, command_contract["parameters"], strict=True):
            if expected["hidden"]:
                continue
            for flag in (*expected["options"], *expected["secondary_options"]):
                if flag.startswith("-"):
                    assert flag in help_result.output, (path, expected["name"], flag)

    global_options = []
    for parameter in root.params:
        metadata = _parameter_metadata(parameter)
        global_options.append(
            {
                "name": metadata["name"],
                "options": metadata["options"],
                "type": metadata["type"],
                "default": metadata["default"],
                "required": metadata["required"],
                "is_flag": metadata["is_flag"],
                "eager": bool(getattr(parameter, "is_eager", False)),
            }
        )
    assert global_options == inventory["global_options"]
