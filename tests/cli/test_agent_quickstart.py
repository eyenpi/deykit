"""A repo-directed agent can complete the documented workflow outside the checkout."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("stdio_encoding", ["utf-8", "cp1252", "ascii"])
def test_agent_quickstart_real_console_and_existing_destination(
    tmp_path: Path, stdio_encoding: str
) -> None:
    script = Path(__file__).parents[2] / "guide/examples/agent-quickstart.py"
    output = tmp_path / "external agent output 東京 ü with spaces"
    environment = {**os.environ, "PYTHONIOENCODING": stdio_encoding}
    command = [sys.executable, str(script), "--output", str(output)]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    summary = json.loads(result.stdout)
    assert summary["status"] == "complete"
    assert summary["evidence_mode"] == "authored_fixture"
    receipts = json.loads(Path(summary["receipts"]).read_text(encoding="utf-8"))
    run_receipts = [item for item in receipts if item["arguments"][0] == "run"]
    assert run_receipts[0]["data"]["initial_requests"] == 1
    assert run_receipts[1]["data"]["run"]["attempts_used"] == 1
    assert run_receipts[2]["data"]["run"]["replayed"] is True
    failures = [item for item in receipts if item["exit_code"] != 0]
    assert len(failures) == 1
    assert failures[0]["exit_code"] == 2
    assert failures[0]["selection"]["choices"]
    report = Path(summary["report"])
    before = report.read_bytes()
    assert json.loads(before)
    repeated = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert repeated.returncode == 2
    assert "output directory must be new" in repeated.stderr
    assert report.read_bytes() == before
