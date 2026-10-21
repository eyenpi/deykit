"""Benchmark-sized report creation/replay/export through the real CLI."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from large_classification_support import COUNT, build_large_evidence

from deykit.storage import FileProjectSource


def test_2500_case_104_option_report_cli_roundtrip(tmp_path):
    configured = os.environ.get("DEYKIT_TEST_CLASSIFICATION_PROJECT")
    project = Path(configured).resolve() if configured else tmp_path / "large project é"
    project.parent.mkdir(parents=True, exist_ok=True)
    evidence = build_large_evidence(project)
    with FileProjectSource(project) as source:
        before = {record.key: record.etag for record in source.capture_snapshot()}
    executable = Path(sys.executable).with_name("deykit.exe" if os.name == "nt" else "deykit")

    def cli(*args):
        result = subprocess.run(
            [str(executable), "--project", str(project), "--json", *args],
            text=True,
            capture_output=True,
            timeout=180,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        envelope = json.loads(result.stdout)
        assert envelope["data"]["success"] is True
        return envelope["data"]

    arguments = (
        "report",
        "export",
        evidence["evaluation_id"],
        "--preset",
        "classification",
        "--target-kind",
        "evaluation",
        "--format",
        "json",
        "--operation-id",
        "large-report",
        "--output",
        str(tmp_path / "report.json"),
    )
    created = cli(*arguments)
    report_id = created["report"]["report_id"]
    assert cli(*arguments)["report"]["report_id"] == report_id
    for format_name in ("csv", "markdown"):
        cli(
            "report",
            "export",
            "--report-id",
            report_id,
            "--format",
            format_name,
            "--output",
            str(tmp_path / f"report.{format_name}"),
        )
    exported = json.loads((tmp_path / "report.json").read_text())
    summary = exported["content"]["classification"]["evaluations"][0]
    assert (summary["selected_count"], summary["applicable_count"], summary["excluded_count"]) == (
        COUNT,
        2498,
        2,
    )
    assert summary["full_cohort_strict_accuracy"]["numerator"] == 2496
    assert summary["full_cohort_strict_accuracy"]["denominator"] == 2498
    assert len(summary["classes"]) == 104
    assert summary["applicable_status_counts"]["response_error"] == 1
    assert summary["applicable_status_counts"]["unknown"] == 1
    evaluation = exported["content"]["evaluations"][0]
    assert len(evaluation["cases"]) == len(evaluation["attempts"]) == COUNT
    assert len(json.loads(evaluation["cases"][2]["probabilities_source"])) == 104
    assert summary["cost"]["total"] is None and summary["cost"]["reason"] == "fixture_no_usage"
    with (tmp_path / "report.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == COUNT
    assert sum(row["strict_correct"] == "true" for row in rows) == 2496
    assert sum(row["strict_correct"] == "false" for row in rows) == 2
    assert sum(row["strict_correct"] == "" for row in rows) == 2
    assert {row["report_id"] for row in rows} == {report_id}
    assert {row["content_hash"] for row in rows} == {exported["content_hash"]}
    assert "2496/2498" in (tmp_path / "report.markdown").read_text()
    with FileProjectSource(project) as source:
        after = {record.key: record.etag for record in source.capture_snapshot()}
    assert all(after.get(key) == etag for key, etag in before.items())
    assert all(key.collection == "reports" for key in after.keys() - before.keys())
