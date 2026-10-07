"""Installed-console report workflows over one copied authored evidence graph."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

pytest_plugins = ("test_reports",)


def _executable() -> Path:
    return Path(sys.executable).with_name("deykit.exe" if os.name == "nt" else "deykit")


def _console(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_executable()), "--project", str(project), "--json", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _payload(result: subprocess.CompletedProcess[str], *, code: int = 0) -> dict[str, object]:
    assert result.returncode == code, (result.stdout, result.stderr)
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    return payload


@pytest.fixture(scope="module")
def cli_report_project(fixture_graph, group_report_graph, tmp_path_factory):
    """Copy the actual cached graph once; CLI writes stay outside the project."""
    parent = tmp_path_factory.mktemp("report-cli-é")
    project = parent / "authored report project é"
    shutil.copytree(group_report_graph.root, project)
    exports = parent / "exported files é"
    exports.mkdir()
    return SimpleNamespace(
        root=project,
        exports=exports,
        fixture=fixture_graph,
        groups=group_report_graph,
    )


def test_installed_console_registers_report_commands_and_flags():
    help_result = subprocess.run(
        [str(_executable()), "--help"], capture_output=True, text=True, timeout=10, check=False
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "report" in help_result.stdout

    for command in (("report", "export"), ("report", "show"), ("report", "list")):
        result = subprocess.run(
            [str(_executable()), *command, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "Usage:" in result.stdout
    export_help = subprocess.run(
        [str(_executable()), "report", "export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    ).stdout
    for option in (
        "--report-id",
        "--target-kind",
        "--evaluation",
        "--result-snapshot",
        "--group-snapshot",
        "--include-raw-inputs",
        "--include-raw-requests",
        "--include-raw-responses",
        "--operation-id",
        "--output",
        "--format",
    ):
        assert option in export_help


def test_console_exports_each_target_and_pinned_group_snapshots(cli_report_project):
    project = cli_report_project
    fixture = project.fixture
    groups = project.groups
    cases = (
        (fixture.run_id, "run", "run-report", "json", ()),
        (fixture.evaluation_id, "evaluation", "evaluation-report", "markdown", ()),
        (fixture.comparison_id, "comparison", "comparison-report", "json", ()),
        (
            groups.diagnostic_group_id,
            "diagnostic",
            "diagnostic-report",
            "markdown",
            ("--group-snapshot", groups.diagnostic_partial_snapshot_id),
        ),
        (
            groups.check_group_id,
            "check",
            "check-report",
            "json",
            ("--group-snapshot", groups.check_partial_snapshot_id),
        ),
    )
    for target, kind, operation, format_name, extra in cases:
        artifact_path = project.exports / f"{operation}.{format_name}"
        result = _console(
            project.root,
            "report",
            "export",
            target,
            "--target-kind",
            kind,
            "--format",
            format_name,
            "--output",
            str(artifact_path),
            "--operation-id",
            operation,
            *extra,
        )
        outcome = _payload(result)["data"]
        assert outcome["success"] is True
        assert outcome["report"]["target_id"] == target
        assert outcome["report"]["target_kind"] == kind
        content_bytes = artifact_path.read_bytes()
        assert hashlib.sha256(content_bytes).hexdigest() == outcome["artifact_hash"]
        if format_name == "json":
            artifact = json.loads(content_bytes)
            assert artifact["content"]["target"]["kind"] == kind
            assert artifact["content"]["target"]["target_id"] == target
            if kind in ("diagnostic", "check"):
                assert artifact["content"]["evaluations"] == []
                assert artifact["content"]["target"]["group_snapshot_id"] == extra[1]

    from deykit.contracts.codec import load_record
    from deykit.contracts.records import EvaluationRecord

    evaluation = next(
        load_record(EvaluationRecord, item.body)
        for item in project.fixture.records
        if item.key.collection == "evaluations"
        and item.key.resource_id == project.fixture.evaluation_id
    )
    for selector, option, value in (
        ("evaluation", "--evaluation", project.fixture.evaluation_id),
        ("result-snapshot", "--result-snapshot", evaluation.result_snapshot_id),
    ):
        artifact_path = project.exports / f"selector-{selector}.json"
        outcome = _payload(
            _console(
                project.root,
                "report",
                "export",
                project.fixture.run_id,
                "--target-kind",
                "run",
                option,
                value,
                "--format",
                "json",
                "--output",
                str(artifact_path),
                "--operation-id",
                f"selector-report-{selector}",
            )
        )["data"]
        assert outcome["success"] is True
        assert outcome["report"]["target_kind"] == "run"
        assert outcome["report"]["evaluation_ids"] == [project.fixture.evaluation_id]
        assert outcome["report"]["result_snapshot_ids"] == [evaluation.result_snapshot_id]

    raw_path = project.exports / "all raw categories.json"
    raw_outcome = _payload(
        _console(
            project.root,
            "report",
            "export",
            project.fixture.run_id,
            "--target-kind",
            "run",
            "--include-raw-inputs",
            "--include-raw-requests",
            "--include-raw-responses",
            "--format",
            "json",
            "--output",
            str(raw_path),
            "--operation-id",
            "actual-raw-all-report",
        )
    )["data"]
    raw_artifact = json.loads(raw_path.read_bytes())
    assert raw_outcome["report"]["raw"] == {
        "inputs": True,
        "requests": True,
        "responses": True,
    }
    assert raw_artifact["content"]["raw"] == raw_outcome["report"]["raw"]
    assert {item["category"] for item in raw_artifact["content"]["raw_material"]} == {
        "input",
        "request",
        "response",
    }


def test_console_failed_destination_keeps_report_identity_and_retry(cli_report_project):
    project = cli_report_project
    protected = project.root / "deykit.project.json"
    original_manifest = protected.read_bytes()
    failed = _console(
        project.root,
        "report",
        "export",
        project.fixture.run_id,
        "--target-kind",
        "run",
        "--format",
        "json",
        "--output",
        str(protected),
        "--operation-id",
        "protected-export-report",
    )
    data = _payload(failed, code=2)["data"]
    assert data["success"] is False
    assert data["destination"] is None
    assert data["report"]["report_id"]
    assert data["artifact_hash"]
    assert data["byte_count"] > 0
    assert data["error"]["reason"] == "export_destination_protected"
    report_id = data["report"]["report_id"]
    assert protected.read_bytes() == original_manifest

    retry_path = project.exports / "saved retry.json"
    retry = _console(
        project.root,
        "report",
        "export",
        "--report-id",
        report_id,
        "--format",
        "json",
        "--output",
        str(retry_path),
    )
    retry_data = _payload(retry)["data"]
    assert retry_data["success"] is True
    assert retry_data["report"]["report_id"] == report_id
    assert hashlib.sha256(retry_path.read_bytes()).hexdigest() == data["artifact_hash"]

    missing_parent_path = project.exports / "missing parent" / "missing-parent.json"
    missing_parent = _console(
        project.root,
        "report",
        "export",
        project.fixture.run_id,
        "--target-kind",
        "run",
        "--format",
        "json",
        "--output",
        str(missing_parent_path),
        "--operation-id",
        "missing-parent-export-report",
    )
    missing_data = _payload(missing_parent, code=2)["data"]
    assert missing_data["success"] is False
    assert missing_data["error"]["reason"] == "export_parent_missing"
    missing_retry = project.exports / "missing parent retry.json"
    missing_retry_result = _console(
        project.root,
        "report",
        "export",
        "--report-id",
        missing_data["report"]["report_id"],
        "--format",
        "json",
        "--output",
        str(missing_retry),
    )
    missing_retry_data = _payload(missing_retry_result)["data"]
    assert missing_retry_data["success"] is True
    assert missing_retry_data["report"]["report_id"] == missing_data["report"]["report_id"]
    assert hashlib.sha256(missing_retry.read_bytes()).hexdigest() == missing_data["artifact_hash"]


def test_console_saved_export_and_metadata_pagination(cli_report_project):
    project = cli_report_project
    artifact = project.exports / "metadata source.json"
    created = _payload(
        _console(
            project.root,
            "report",
            "export",
            project.fixture.run_id,
            "--target-kind",
            "run",
            "--format",
            "json",
            "--output",
            str(artifact),
            "--operation-id",
            "metadata-report-operation",
        )
    )["data"]
    report_id = created["report"]["report_id"]
    shown = _payload(_console(project.root, "report", "show", report_id))["data"]
    assert shown["report_id"] == report_id
    assert "content" not in shown and "raw_material" not in shown

    first_page = _payload(
        _console(project.root, "report", "list", "--limit", "1")
    )["data"]
    assert len(first_page["items"]) == 1
    assert first_page["next_cursor"] is not None
    assert "content" not in first_page["items"][0]
    second_page = _payload(
        _console(
            project.root,
            "report",
            "list",
            "--limit",
            "1",
            "--cursor",
            first_page["next_cursor"],
        )
    )["data"]
    assert second_page["items"][0]["report_id"] > first_page["items"][0]["report_id"]


@pytest.mark.parametrize(
    "args, reason",
    (
        (("report", "export", "--output", "out.json"), "invalid_report_selector"),
        (
            ("report", "export", "target", "--report-id", "saved", "--output", "out.json"),
            "invalid_report_selector",
        ),
        (
            ("report", "export", "target", "--format", "xml", "--output", "out.xml"),
            "invalid_report_format",
        ),
        (
            (
                "report",
                "export",
                "target",
                "--target-kind",
                "unknown",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--evaluation",
                "evaluation",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--target-kind",
                "run",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--result-snapshot",
                "result",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--group-snapshot",
                "group",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--include-raw-requests",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--include-raw-responses",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--include-raw-inputs",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
        (
            (
                "report",
                "export",
                "--report-id",
                "saved",
                "--operation-id",
                "op",
                "--output",
                "out.json",
            ),
            "invalid_report_selector",
        ),
    ),
)
def test_invalid_export_input_fails_before_project_access(tmp_path, args, reason):
    from deykit.cli.main import app

    result = CliRunner().invoke(
        app,
        ["--project", str(tmp_path / "missing project"), "--json", *args],
    )
    assert result.exit_code == 2
    assert result.output.count("\n") == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["error"]["reason"] == reason
    assert not (tmp_path / "missing project").exists()


def test_missing_output_is_a_safe_parser_error_before_project_access(tmp_path):
    from deykit.cli.main import app

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path / "missing project"),
            "--json",
            "report",
            "export",
            "target",
        ],
    )
    assert result.exit_code == 2
    assert result.output.count("\n") == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["error"]["reason"] == "invalid_command"
    assert not (tmp_path / "missing project").exists()


def test_all_raw_flag_combinations_reach_the_service_independently(tmp_path, monkeypatch):
    from deykit.cli import context as context_module
    from deykit.cli.commands import reports as reports_module
    from deykit.reports.models import ExportOutcome, ReportMetadata

    requests = []
    metadata_raw = []

    class FakeSource:
        root = tmp_path

    @contextmanager
    def source(_cli):
        yield FakeSource()

    class Service:
        def __init__(self, _source, _clock):
            self.sanitizer = SimpleNamespace()

        def create(self, request, *, operation_id):
            requests.append((request, operation_id))
            record = SimpleNamespace(id=f"report-{len(requests)}")
            return SimpleNamespace(record=record)

        def export(self, report_id, *, format, destination, writer):
            request = requests[-1][0]
            metadata_raw.append(request.raw)
            metadata = ReportMetadata(
                report_id=report_id,
                content_hash="a" * 64,
                created_at="2026-10-07T00:00:00Z",
                target_id=request.target_id,
                target_kind=request.target_kind or "run",
                raw=request.raw,
            )
            return ExportOutcome(
                report=metadata,
                format=format,
                success=True,
                destination=str(destination),
                requested_destination=str(destination),
                artifact_hash="b" * 64,
                byte_count=1,
            )

    monkeypatch.setattr(context_module.CliState, "source", source)
    monkeypatch.setattr(reports_module, "ReportService", Service)
    monkeypatch.setattr(
        reports_module,
        "NativeArtifactWriter",
        lambda *_args, **_kwargs: object(),
    )
    from deykit.cli.main import app

    for mask in range(8):
        args = [
            "--project",
            str(tmp_path),
            "report",
            "export",
            "run-target",
            "--format",
            "json",
            "--output",
            str(tmp_path / f"{mask}.json"),
            "--operation-id",
            f"raw-flags-{mask}",
        ]
        expected = tuple(bool(mask & bit) for bit in (1, 2, 4))
        args.extend(
            flag
            for enabled, flag in zip(
                expected,
                ("--include-raw-inputs", "--include-raw-requests", "--include-raw-responses"),
            )
            if enabled
        )
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert requests[-1][0].raw.inputs is expected[0]
        assert requests[-1][0].raw.requests is expected[1]
        assert requests[-1][0].raw.responses is expected[2]
    assert len(requests) == 8
    assert len(metadata_raw) == 8


def test_human_durability_warning_keeps_success_exit_and_reports_warning(tmp_path, monkeypatch):
    from deykit.cli import context as context_module
    from deykit.cli.commands import reports as reports_module
    from deykit.contracts.errors import ServiceError
    from deykit.reports.models import ExportOutcome, ReportMetadata

    warning = ServiceError(code="internal_error", reason="export_durability_unconfirmed")
    metadata = ReportMetadata(
        report_id="warning-report",
        content_hash="a" * 64,
        created_at="2026-10-07T00:00:00Z",
        target_id="run-target",
        target_kind="run",
    )

    class FakeSource:
        root = tmp_path

    @contextmanager
    def source(_cli):
        yield FakeSource()

    class Service:
        sanitizer = SimpleNamespace()

        def __init__(self, _source, _clock):
            pass

        def create(self, request, *, operation_id):
            return SimpleNamespace(record=SimpleNamespace(id=metadata.report_id))

        def export(self, report_id, *, format, destination, writer):
            return ExportOutcome(
                report=metadata,
                format=format,
                success=True,
                destination="/safe/report.json",
                requested_destination=destination,
                artifact_hash="b" * 64,
                byte_count=12,
                durability_warning=warning,
            )

    monkeypatch.setattr(context_module.CliState, "source", source)
    monkeypatch.setattr(reports_module, "ReportService", Service)
    monkeypatch.setattr(reports_module, "NativeArtifactWriter", lambda *_args, **_kwargs: object())
    from deykit.cli.main import app

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "report",
            "export",
            "run-target",
            "--output",
            str(tmp_path / "report.json"),
            "--operation-id",
            "warning-operation",
        ],
    )
    assert result.exit_code == 0
    assert "warning-report" in result.output
    assert "destination_status" in result.output
    assert "export_durability_unconfirmed" in result.stderr

    json_result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--json",
            "report",
            "export",
            "run-target",
            "--format",
            "json",
            "--output",
            str(tmp_path / "report.json"),
            "--operation-id",
            "warning-operation-json",
        ],
    )
    assert json_result.exit_code == 0
    assert json_result.stderr == ""
    assert json_result.output.count("\n") == 1
    json_outcome = json.loads(json_result.output)
    assert json_outcome["data"]["success"] is True
    assert json_outcome["warnings"][0]["reason"] == "export_durability_unconfirmed"
