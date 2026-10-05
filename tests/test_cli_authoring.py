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
