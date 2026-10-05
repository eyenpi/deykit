"""Installed CLI inspection and zero-call reevaluation use the same real source."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from deykit.runner.planner import RunRequest


def command(project: Path, *args: str) -> dict[str, object]:
    process = subprocess.run(
        [
            str(Path(sys.executable).with_name("deykit")),
            "--project",
            str(project),
            "--json",
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, (process.stderr, process.stdout)
    assert process.stderr == ""
    assert process.stdout.count("\n") == 1
    payload = json.loads(process.stdout)
    assert payload["schema_version"] == 1
    return payload["data"]


def test_cli_list_show_annotate_and_reevaluate_saved_answers(setup):
    source, runner, factory, _ = setup(2, invalid=(1,))
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    listing = command(source.root, "results", "list", run.run_id)
    assert listing["selected_count"] == 2
    assert listing["status_counts"]["input_invalid"] == 1
    assert listing["filtered_count"] == 2
    shown = command(source.root, "results", "show", run.run_id, "case-00")
    assert shown["status"] == "valid" and shown["attempts"] == []
    assert shown["input_source"] is None
    detailed = command(source.root, "results", "show", run.run_id, "case-00", "--attempts")
    assert detailed["attempts"][0]["request_body_hash"] == factory.calls[0][1].body_hash
    assert "request_body_source" not in detailed["attempts"][0]
    saved_note = command(
        source.root,
        "results",
        "annotate",
        run.run_id,
        "case-00",
        "--note",
        "Follow up",
        "--operation-id",
        "note-op",
    )
    assert saved_note["annotation_id"]
    replay = command(
        source.root,
        "results",
        "annotate",
        run.run_id,
        "case-00",
        "--note",
        "Follow up",
        "--operation-id",
        "note-op",
    )
    assert replay["annotation_id"] == saved_note["annotation_id"] and replay["replayed"]
    rescored = command(source.root, "reevaluate", run.run_id, "--operation-id", "rescore")
    assert rescored["dispatch_count"] == 0
    assert rescored["metrics"]["summary"]["selected_count"] == 2
    assert len(factory.calls) == 1
    assert (
        command(source.root, "results", "show", run.run_id, "case-00")["annotations"][0]["note"]
        == "Follow up"
    )
