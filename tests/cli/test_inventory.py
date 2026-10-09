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


def _parameter(command, name: str):
    return next(parameter for parameter in command.params if parameter.name == name)


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
    assert implemented == _leaves(command_root)
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
    for path in sorted(implemented):
        result = runner.invoke(app, [*path.split(), "--help"])
        assert result.exit_code == 0, path
        assert "Usage:" in result.output, path


def test_documented_cli_parameter_inventory_matches_typer_metadata() -> None:
    root = get_command(app)
    assert isinstance(root, TyperGroup)

    fixture_create = _command(root, ("fixture", "create"))
    decision = _parameter(fixture_create, "decision")
    assert decision.opts == ["--decision"]
    assert decision.type.name == "text"
    assert decision.required is True
    assert decision.default is None

    file_option = _parameter(fixture_create, "file")
    assert file_option.opts == ["--file"]
    assert file_option.type.name == "path"
    assert file_option.required is False
    assert file_option.default is None

    stdin_option = _parameter(fixture_create, "stdin")
    assert stdin_option.opts == ["--stdin"]
    assert stdin_option.type.name == "boolean"
    assert stdin_option.default is False

    fixture_list = _command(root, ("fixture", "list"))
    page_limit = _parameter(fixture_list, "limit")
    assert page_limit.opts == ["--limit"]
    assert page_limit.type.name == "integer"
    assert page_limit.default == 50

    result_show = _command(root, ("results", "show"))
    run_argument = _parameter(result_show, "run_id")
    assert run_argument.type.name == "text"
    assert run_argument.required is True

    report_export = _command(root, ("report", "export"))
    report_target = _parameter(report_export, "target_id")
    assert report_target.type.name == "text"
    assert report_target.required is False
    target_kind = _parameter(report_export, "target_kind")
    assert target_kind.opts == ["--target-kind"]
    assert target_kind.type.name == "choice"
    assert target_kind.default is None

    runner = CliRunner()
    for path, flags in (
        (("fixture", "create"), ("--decision", "--dataset", "--file", "--stdin")),
        (("fixture", "list"), ("--cursor", "--limit")),
        (("results", "show"), ("--evaluation", "--request", "--response", "--attempts")),
        (("report", "export"), ("--target-kind", "--result-snapshot", "--output")),
    ):
        help_result = runner.invoke(app, [*path, "--help"])
        assert help_result.exit_code == 0, help_result.output
        for flag in flags:
            assert flag in help_result.output, (" ".join(path), flag)
