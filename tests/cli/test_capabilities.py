"""Agents discover actual command parameters without credentials or project access."""

import json
from pathlib import Path

from typer.testing import CliRunner

from deykit.cli.context import CliState
from deykit.cli.main import app

cli = CliRunner()


def test_capabilities_without_project_or_credentials(monkeypatch, tmp_path: Path) -> None:
    def forbidden_source(self):
        raise AssertionError("discovery must not open a project")

    monkeypatch.setattr(CliState, "source", forbidden_source)
    result = cli.invoke(app, ["--project", str(tmp_path / "missing"), "--json", "capabilities"])
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    data = json.loads(result.stdout)["data"]
    paths = {tuple(item["path"]) for item in data["commands"]}
    assert {("run",), ("results", "show"), ("capabilities",)} <= paths
    assert data["interface_version"] == 1
    assert data["exit_codes"]["4"].startswith("incomplete")
    assert not (tmp_path / "missing").exists()


def test_capabilities_parameters_match_published_parser_contract() -> None:
    inventory = json.loads(
        (Path(__file__).parents[2] / "architecture/cli-parameter-inventory.json").read_text()
    )
    for path in ("run", "results show", "dataset import", "capabilities"):
        result = cli.invoke(app, ["--json", "capabilities", *path.split()])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)["data"]
        assert data["command"]["parameters"] == inventory["commands"][path]["parameters"]
        assert "commands" not in data


def test_capabilities_group_and_invalid_path() -> None:
    result = cli.invoke(app, ["--json", "capabilities", "results"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["command"]["kind"] == "group"
    for path in (("missing",), ("run", "missing")):
        result = cli.invoke(app, ["--json", "capabilities", *path])
        assert result.exit_code == 2
        assert json.loads(result.stdout)["error"]["reason"] == "unknown_command_path"
        assert result.stderr == ""
