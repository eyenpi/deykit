"""The published command matrix covers every registered CLI leaf exactly once."""

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
        assert set(row["verification"]) == {"registration", "behavior"}
        if row["status"] == "planned":
            assert row["verification"] == {"registration": "pending", "behavior": "pending"}
            continue
        for reference in row["verification"].values():
            if reference.startswith(("tests/", "src/")):
                relative_path, _, symbol = reference.partition("::")
                target = matrix_path.parents[1] / relative_path
                assert target.is_file(), reference
                if symbol:
                    assert symbol.split(".")[-1] in target.read_text(encoding="utf-8"), reference

    runner = CliRunner()
    for path in sorted(_groups(command_root)):
        result = runner.invoke(app, [*path, "--help"] if path else ["--help"])
        assert result.exit_code == 0, " ".join(path)
        assert "Usage:" in result.output, " ".join(path)
    for path in sorted(implemented):
        result = runner.invoke(app, [*path.split(), "--help"])
        assert result.exit_code == 0, path
        assert "Usage:" in result.output, path
