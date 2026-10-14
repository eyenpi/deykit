#!/usr/bin/env python3
"""Exercise discovery, preview, fixture execution, replay and reports via the real CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def quickstart(output: Path) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    executable = Path(sys.executable).with_name("deykit.exe" if os.name == "nt" else "deykit")
    project = output / "Agent demo ü with spaces"
    receipts: list[dict[str, Any]] = []

    def call(*arguments: str, expected: int = 0) -> dict[str, Any]:
        result = subprocess.run(
            [str(executable), "--project", str(project), "--json", *arguments],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        envelope = json.loads(result.stdout)
        receipts.append({"arguments": list(arguments), "exit_code": result.returncode, **envelope})
        (output / "receipts.json").write_text(
            json.dumps(receipts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if result.returncode != expected or envelope.get("schema_version") != 1:
            raise RuntimeError(f"Unexpected CLI outcome for {arguments}: {envelope}")
        return envelope.get("data", envelope)

    call("capabilities", "run")
    info = call("demo", str(project), "--operation-id", "agent-demo")["info"]
    call("project", "validate")
    cases = call("case", "list", "--dataset", info["dataset_id"])
    case_id = cases["items"][0]["record"]["id"]
    arguments = (
        "run",
        "--decision",
        info["decision_id"],
        "--revision",
        info["revision_id"],
        "--dataset",
        info["dataset_id"],
        "--case",
        case_id,
        "--mode",
        "fixture",
        "--fixture-set",
        info["fixture_set_id"],
        "--attempt-limit",
        "1",
        "--concurrency",
        "1",
        "--rate-retries",
        "0",
    )
    preview = call(*arguments, "--dry-run")
    if preview["selected_case_ids"] != [case_id] or preview["initial_requests"] != 1:
        raise RuntimeError("Preview did not select exactly one authored request")
    if call("runs", "list")["total"] != 0:
        raise RuntimeError("Preview created execution evidence")
    first = call(*arguments, "--operation-id", "agent-first-run")["run"]
    replay = call(*arguments, "--operation-id", "agent-first-run")["run"]
    if first["run_id"] != replay["run_id"] or not replay["replayed"]:
        raise RuntimeError("Run replay did not preserve the original identity")
    if call("runs", "list")["total"] != 1 or replay["attempts_used"] != 1:
        raise RuntimeError("Replay created another run or consumed another attempt")
    call("results", "show", first["run_id"], case_id)
    call("results", "show", first["run_id"], "missing-case", expected=2)
    report_path = output / "report.json"
    report = call(
        "report",
        "export",
        first["run_id"],
        "--target-kind",
        "run",
        "--format",
        "json",
        "--output",
        str(report_path),
        "--operation-id",
        "agent-report",
    )
    json.loads(report_path.read_text(encoding="utf-8"))
    call("project", "validate")
    summary = {
        "schema_version": 1,
        "status": "complete",
        "evidence_mode": info["evidence_mode"],
        "project": str(project),
        "run_id": first["run_id"],
        "report_id": report["report"]["report_id"],
        "report": str(report_path),
        "receipts": str(output / "receipts.json"),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory.")
    arguments = parser.parse_args()
    if arguments.output.exists():
        parser.error("output directory must be new")
    print(json.dumps(quickstart(arguments.output.absolute())))


if __name__ == "__main__":
    main()
