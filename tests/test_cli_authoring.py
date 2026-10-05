"""Installed, browser-free CLI checks through real subprocesses and Typer's runner."""

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from deykit.cli.main import app
from deykit.contracts.codec import dump_record
from deykit.contracts.records import ChoiceDefinition, ChoiceOption, ChoiceQuestion


def cli(cwd: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("deykit")
    return subprocess.run(
        [str(executable), *args],
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def result(process: subprocess.CompletedProcess[str], expected_code: int = 0) -> dict[str, object]:
    assert process.returncode == expected_code, process.stderr
    assert process.stderr == ""
    assert process.stdout.count("\n") == 1
    payload = json.loads(process.stdout)
    assert payload["schema_version"] == 1
    return payload


def definition() -> str:
    return dump_record(
        ChoiceDefinition(
            input_kind="json",
            input_schema_source='{"type":"object","required":["shown"]}',
            selected_fields=("shown",),
            questions=(
                ChoiceQuestion(
                    id="q",
                    instructions="Choose",
                    options=(ChoiceOption(id="a", name="A"), ChoiceOption(id="b", name="B")),
                ),
            ),
        )
    ).decode()


def test_cli_help_and_json_parser_error(tmp_path: Path) -> None:
    runner = CliRunner()
    root_help = runner.invoke(app, ["--help"])
    assert root_help.exit_code == 0
    assert all(
        name in root_help.output for name in ("init", "project", "decision", "dataset", "case")
    )
    for group in ("project", "decision", "dataset", "case"):
        assert runner.invoke(app, [group, "--help"]).exit_code == 0
    malformed = result(cli(tmp_path, "--json", "nonsense"), 2)
    assert malformed["error"]["reason"] == "invalid_command"
    assert "Traceback" not in json.dumps(malformed)


def test_machine_readable_inventory_matches_registered_help() -> None:
    matrix = json.loads(
        (Path(__file__).parents[1] / "architecture" / "cli-command-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    runner = CliRunner()
    for entry in matrix["commands"]:
        assert set(entry["verification"]) == {"registration", "behavior"}
        if entry["status"] == "implemented":
            help_result = runner.invoke(app, [*entry["path"].split(), "--help"])
            assert help_result.exit_code == 0, entry["path"]
            assert "Usage:" in help_result.output, entry["path"]


def test_cli_project_discovery_exact_source_conflict_and_replay(tmp_path: Path) -> None:
    root = tmp_path / "Project ü with spaces"
    initial = result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    assert initial["data"]["info"]["project"]["name"] == "P"
    inside = root / "nested"
    inside.mkdir()
    created = result(
        cli(
            inside,
            "--json",
            "decision",
            "create",
            "d",
            "--name",
            "D",
            "--stdin",
            input_text=definition(),
        )
    )
    table = cli(inside, "decision", "list")
    assert table.returncode == 0
    assert "ID\tNAME\tSTATUS" in table.stdout and "d\tD\tdraft" in table.stdout
    draft_hash = created["data"]["result"]["draft"]["etag"]
    pointer_hash = created["data"]["result"]["decision"]["etag"]
    saved = result(
        cli(
            inside,
            "--json",
            "decision",
            "save",
            "d",
            "--if-draft-hash",
            draft_hash,
            "--if-decision-hash",
            pointer_hash,
            "--operation-id",
            "save-first",
        )
    )
    same = result(
        cli(
            inside,
            "--json",
            "decision",
            "save",
            "d",
            "--if-draft-hash",
            draft_hash,
            "--if-decision-hash",
            pointer_hash,
            "--operation-id",
            "save-first",
        )
    )
    assert same["data"]["result"] == saved["data"]["result"]
    changed = result(
        cli(
            inside,
            "--json",
            "decision",
            "save",
            "d",
            "--note",
            "different",
            "--if-draft-hash",
            draft_hash,
            "--if-decision-hash",
            pointer_hash,
            "--operation-id",
            "save-first",
        ),
        2,
    )
    assert changed["error"]["code"] == "conflict"
    stale = result(
        cli(
            inside,
            "--json",
            "decision",
            "edit",
            "d",
            "--stdin",
            "--if-hash",
            "0" * 64,
            input_text="invalid but retained locally",
        ),
        2,
    )
    assert stale["error"]["code"] == "conflict"
    shown = result(cli(inside, "--json", "decision", "show", "d"))
    assert shown["data"]["draft"]["record"]["editor_source"] == definition()
    assert result(cli(inside, "--json", "project", "validate"))["data"]["info"]["record_count"] >= 3


def test_cli_case_file_and_stdin_preserve_precise_input(tmp_path: Path) -> None:
    root = tmp_path / "p"
    result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    result(cli(root, "--json", "dataset", "create", "data", "--name", "Data"))
    precise = '{"shown":9007199254740993,"hidden":0.1234567890123456789}'
    case_input = json.dumps({"input_kind": "json", "input_source": precise})
    path = tmp_path / "case.json"
    path.write_text(case_input, encoding="utf-8")
    added = result(
        cli(root, "--json", "case", "add", "--dataset", "data", "--id", "case", "--file", str(path))
    )
    assert added["data"]["result"]["case"]["record"]["input_source"] == precise
    shown = result(cli(root, "--json", "case", "show", "case", "--dataset", "data"))
    assert shown["data"]["record"]["input_source"] == precise
    conflict = result(
        cli(
            root,
            "--json",
            "case",
            "edit",
            "case",
            "--dataset",
            "data",
            "--file",
            str(path),
            "--stdin",
            input_text=case_input,
        ),
        2,
    )
    assert conflict["error"]["reason"] == "input_mode_conflict"


def test_cli_import_preview_default_abort_and_explicit_partial(tmp_path: Path) -> None:
    root = tmp_path / "p"
    result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    result(
        cli(
            root,
            "--json",
            "decision",
            "create",
            "d",
            "--name",
            "D",
            "--stdin",
            input_text=definition(),
        )
    )
    result(cli(root, "--json", "dataset", "create", "data", "--name", "Data"))
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        '{"schema_version":1,"input_kind":"json","input_column":"input","id_column":"id"}',
        encoding="utf-8",
    )
    rows = (
        '{"id":"good","input":{"shown":9007199254740993}}\n'
        '{"id":"bad","input":{"hidden":"PRIVATE"}}\n'
    )
    common = (
        "--json",
        "dataset",
        "import",
        "data",
        "--format",
        "jsonl",
        "--mapping",
        str(mapping),
        "--decision",
        "d",
        "--stdin",
    )
    preview = result(cli(root, *common, "--dry-run", input_text=rows))
    assert preview["data"]["would_import"] == 1
    assert preview["data"]["preview"]["rows"][1]["errors"][0]["reason"] == "input_schema_mismatch"
    failed = result(cli(root, *common, input_text=rows), 2)
    assert failed["error"]["reason"] == "import_rows_invalid"
    assert result(cli(root, "--json", "case", "list", "--dataset", "data"))["data"]["total"] == 0
    imported = result(cli(root, *common, "--skip-invalid", input_text=rows))
    assert imported["data"]["result"]["imported_case_ids"] == ["good"]
    shown = result(cli(root, "--json", "case", "show", "good", "--dataset", "data"))
    assert shown["data"]["record"]["input_source"] == '{"shown":9007199254740993}'


def test_cli_label_review_replay_batch_and_transitions(tmp_path: Path) -> None:
    root = tmp_path / "p"
    result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    result(
        cli(
            root,
            "--json",
            "decision",
            "create",
            "d",
            "--name",
            "D",
            "--stdin",
            input_text=definition(),
        )
    )
    result(cli(root, "--json", "dataset", "create", "data", "--name", "Data"))
    for case_id in ("first", "second"):
        value = json.dumps({"input_kind": "json", "input_source": '{"shown":"hello"}'})
        result(
            cli(
                root,
                "--json",
                "case",
                "add",
                "--dataset",
                "data",
                "--id",
                case_id,
                "--stdin",
                input_text=value,
            )
        )
    review = result(
        cli(root, "--json", "label", "show", "first", "--decision", "d", "--dataset", "data")
    )
    review_file = tmp_path / "review.json"
    review_file.write_text(json.dumps(review), encoding="utf-8")
    same_args = (
        "--json",
        "label",
        "set",
        "first",
        "--decision",
        "d",
        "--dataset",
        "data",
        "--expected",
        "a",
        "--provenance",
        "human",
        "--review",
        str(review_file),
        "--operation-id",
        "set-first",
    )
    original = result(cli(root, *same_args))
    assert result(
        cli(root, "--json", "label", "history", "first", "--decision", "d", "--dataset", "data")
    )["data"]
    disputed = result(
        cli(
            root,
            "--json",
            "label",
            "dispute",
            "first",
            "--decision",
            "d",
            "--dataset",
            "data",
            "--reason",
            "Needs review",
        )
    )
    assert disputed["data"]["result"]["changes"][0]["label"]["status"] == "disputed"
    replay = result(cli(root, *same_args))
    assert replay["data"]["result"]["changes"] == original["data"]["result"]["changes"]
    changed = result(
        cli(root, *same_args[:-2], "--operation-id", "set-first", "--expected", "b"), 2
    )
    assert changed["error"]["code"] == "conflict"
    resolved = result(
        cli(
            root,
            "--json",
            "label",
            "resolve",
            "first",
            "--decision",
            "d",
            "--dataset",
            "data",
            "--expected",
            "b",
        )
    )
    assert resolved["data"]["result"]["changes"][0]["label"]["status"] == "active"
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": [
                    {"case_id": "first", "action": "clear"},
                    {
                        "case_id": "second",
                        "action": "set",
                        "expected": ["a"],
                        "provenance": "human",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    batch = result(
        cli(
            root,
            "--json",
            "label",
            "set",
            "--decision",
            "d",
            "--dataset",
            "data",
            "--file",
            str(batch_file),
        )
    )
    assert sorted(item["action"] for item in batch["data"]["result"]["changes"]) == [
        "clear",
        "set",
    ]
    assert (
        result(cli(root, "--json", "label", "list", "--decision", "d", "--dataset", "data"))[
            "data"
        ]["total"]
        == 2
    )


def test_cli_split_exact_ratios_and_group_conflict(tmp_path: Path) -> None:
    root = tmp_path / "p"
    result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    result(cli(root, "--json", "dataset", "create", "data", "--name", "Data"))
    assert result(cli(root, "--json", "dataset", "list"))["data"]["total"] == 1
    for case_id in ("a", "b"):
        value = json.dumps({"input_kind": "text", "input_source": '"same"'})
        result(
            cli(
                root,
                "--json",
                "case",
                "add",
                "--dataset",
                "data",
                "--id",
                case_id,
                "--stdin",
                input_text=value,
            )
        )
    preview = result(
        cli(
            root,
            "--json",
            "dataset",
            "split",
            "data",
            "--development",
            "0.6000000000000001",
            "--calibration",
            "0.2",
            "--dry-run",
        )
    )
    assert (
        preview["data"]["preview"]["ratios_source"]
        == '{"development":0.6000000000000001,"calibration":0.2,"test":0.1999999999999999}'
    )
    assignment_file = tmp_path / "assignments.json"
    assignment_file.write_text('{"a":"development","b":"test"}', encoding="utf-8")
    invalid = result(
        cli(root, "--json", "dataset", "split", "data", "--assignments", str(assignment_file)), 2
    )
    assert invalid["error"]["reason"] == "conflicting_group_assignments"
    applied = result(cli(root, "--json", "dataset", "split", "data", "--seed", "42"))
    pairs = applied["data"]["result"]["snapshot"]["cases"]
    assert pairs[0]["split"] == pairs[1]["split"]


def test_cli_remaining_authoring_transitions_and_pagination(tmp_path: Path) -> None:
    root = tmp_path / "project"
    result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    project = result(cli(root, "--json", "project", "show"))
    assert project["data"]["info"]["project"]["name"] == "P"
    result(cli(root, "--json", "project", "rebuild-index"))
    result(
        cli(
            root,
            "--json",
            "decision",
            "create",
            "d",
            "--name",
            "D",
            "--stdin",
            input_text=definition(),
        )
    )
    validation = result(cli(root, "--json", "decision", "validate", "d"))
    assert validation["data"]["input_kind"] == "json"
    saved = result(cli(root, "--json", "decision", "save", "d"))
    revision_id = saved["data"]["result"]["record"]["id"]
    assert result(cli(root, "--json", "decision", "history", "d"))["data"]["total"] == 1
    result(cli(root, "--json", "decision", "show", "d", "--revision", revision_id))
    result(cli(root, "--json", "decision", "diff", "d", revision_id, "draft"))
    renamed = result(cli(root, "--json", "decision", "rename", "d", "--name", "D2"))
    assert renamed["data"]["result"]["record"]["name"] == "D2"
    result(cli(root, "--json", "decision", "archive", "d"))
    result(cli(root, "--json", "decision", "restore", "d"))
    result(cli(root, "--json", "decision", "edit", "d", "--from-revision", revision_id))

    result(cli(root, "--json", "dataset", "create", "data", "--name", "Data"))
    result(cli(root, "--json", "dataset", "show", "data"))
    edited = result(cli(root, "--json", "dataset", "edit", "data", "--name", "Updated"))
    assert edited["data"]["result"]["record"]["name"] == "Updated"
    result(cli(root, "--json", "dataset", "archive", "data"))
    result(cli(root, "--json", "dataset", "restore", "data"))
    case_source = '{"input_kind":"json","input_source":"{\\"shown\\":1}"}'
    result(
        cli(
            root,
            "--json",
            "case",
            "add",
            "--dataset",
            "data",
            "--id",
            "a",
            "--stdin",
            input_text=case_source,
        )
    )
    result(
        cli(
            root,
            "--json",
            "case",
            "add",
            "--dataset",
            "data",
            "--id",
            "b",
            "--stdin",
            input_text=case_source,
        )
    )
    edited_case = result(
        cli(
            root,
            "--json",
            "case",
            "edit",
            "b",
            "--dataset",
            "data",
            "--stdin",
            input_text=case_source,
        )
    )
    assert edited_case["data"]["result"]["case"]["record"]["id"] == "b"
    first = result(cli(root, "--json", "case", "list", "--dataset", "data", "--limit", "1"))
    assert len(first["data"]["items"]) == 1
    assert first["data"]["next_cursor"] is not None
    second = result(
        cli(
            root,
            "--json",
            "case",
            "list",
            "--dataset",
            "data",
            "--limit",
            "1",
            "--cursor",
            first["data"]["next_cursor"],
        )
    )
    assert len(second["data"]["items"]) == 1
    assert second["data"]["items"][0]["record"]["id"] != first["data"]["items"][0]["record"]["id"]
    result(cli(root, "--json", "case", "remove", "a", "--dataset", "data"))
    assert result(cli(root, "--json", "case", "list", "--dataset", "data"))["data"]["total"] == 1


def test_cli_invalid_utf8_and_explicit_editor_are_safe(tmp_path: Path) -> None:
    root = tmp_path / "p"
    result(cli(tmp_path, "--json", "init", str(root), "--name", "P"))
    result(cli(root, "--json", "decision", "create", "d", "--name", "D"))
    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b"\xff")
    bad = result(cli(root, "--json", "decision", "edit", "d", "--file", str(malformed)), 2)
    assert bad["error"]["reason"] == "invalid_utf8"
    editor = result(cli(root, "--json", "decision", "edit", "d", "--editor"), 2)
    assert editor["error"]["reason"] == "interactive_required"
    assert (
        result(cli(root, "--json", "decision", "show", "d"))["data"]["draft"]["record"][
            "editor_source"
        ]
        == ""
    )
    result(cli(root, "--json", "decision", "edit", "d", "--stdin", input_text="unfinished {"))
    assert (
        result(cli(root, "--json", "decision", "show", "d"))["data"]["draft"]["record"][
            "editor_source"
        ]
        == "unfinished {"
    )
    invalid_save = result(cli(root, "--json", "decision", "save", "d"), 2)
    assert invalid_save["error"]["code"] == "validation_error"


def test_cli_demo_creates_actual_authored_project_ids(tmp_path: Path) -> None:
    created = result(cli(tmp_path, "--json", "demo", "sandbox", "--operation-id", "demo-once"))
    info = created["data"]["info"]
    assert created["data"]["operation_id"] == "demo-once"
    assert info["path"] == str(tmp_path / "sandbox")
    assert (info["case_count"], info["binding_count"], info["label_count"]) == (12, 11, 9)
    assert info["evidence_mode"] == "authored_fixture"
    project = result(cli(tmp_path / "sandbox", "--json", "project", "show"))
    assert project["data"]["info"]["project"]["id"] == info["project_id"]
    decision = result(cli(tmp_path / "sandbox", "--json", "decision", "show", info["decision_id"]))
    assert decision["data"]["decision"]["record"]["latest_revision_id"] == info["revision_id"]
    dataset = result(cli(tmp_path / "sandbox", "--json", "dataset", "show", info["dataset_id"]))
    assert dataset["data"]["cases"]["total"] == 12
    conflict = result(cli(tmp_path, "--json", "demo", "sandbox"), 2)
    assert conflict["error"]["reason"] == "demo_path_exists"
