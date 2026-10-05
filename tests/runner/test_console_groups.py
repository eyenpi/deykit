"""The real console binary and exact FixtureSet adapter; no service monkeypatch."""

import os
import re
import subprocess
import sys
from pathlib import Path


def test_real_console_diagnostics_regressions_fixture_flow(tmp_path):
    script = Path(__file__).parents[1] / "p12_console_probe.py"
    executable = Path(sys.executable).parent / ("deykit.exe" if os.name == "nt" else "deykit")
    result = subprocess.run(
        [sys.executable, str(script), str(executable), str(tmp_path / "project é")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS P12 offline real-console fixture flow" in result.stdout


def test_group_commands_registered_with_explicit_help():
    from typer.testing import CliRunner

    from deykit.cli.main import app

    runner = CliRunner()
    for command in (
        ("diagnose", "choice-order"),
        ("diagnose", "show"),
        ("diagnose", "resume"),
        ("regression", "add"),
        ("regression", "list"),
        ("regression", "remove"),
        ("check",),
        ("checks", "show"),
        ("checks", "resume"),
    ):
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["regression", "add", "--help"])
    plain_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--provenance" in plain_output
