from pathlib import Path

import pytest
from typer.testing import CliRunner

from deykit.cli.commands import serve as serve_module
from deykit.cli.main import app


def test_serve_forwards_project_and_port(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "Project"
    calls: list[tuple[Path | None, int]] = []
    monkeypatch.setattr(
        serve_module,
        "launch_local_server",
        lambda path, *, port: calls.append((path, port)),
    )
    result = CliRunner().invoke(app, ["--project", str(project), "serve", "--port", "0"])
    assert result.exit_code == 0, result.output
    assert calls == [(project, 0)]


@pytest.mark.parametrize("command,flag", [("serve", "--no-open"), ("demo", "--open")])
def test_removed_browser_flags_fail_before_creating_a_project(
    tmp_path: Path, command: str, flag: str
) -> None:
    target = tmp_path / "Sandbox"
    arguments = ["demo", str(target), flag] if command == "demo" else [command, flag]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 2
    assert not target.exists()
