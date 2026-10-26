"""Two full benchmark cohorts retain their evidence through the installed CLI."""

import csv
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from large_classification_support import COUNT, build_large_evidence

from deykit.contracts.codec import load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import ResultSnapshot
from deykit.storage import FileProjectSource


def test_2500_pair_104_option_classification_report(tmp_path):
    configured = os.environ.get("DEYKIT_TEST_CLASSIFICATION_COMPARISON_PROJECT")
    project = Path(configured).resolve() if configured else tmp_path / "paired project é"
    project.parent.mkdir(parents=True, exist_ok=True)
    evidence = build_large_evidence(project, paired=True)
    assert evidence["calls"] == 5000
    with FileProjectSource(project) as source:
        records = source.capture_snapshot()
        before = {record.key: record.etag for record in records}
        saved_vectors = {}
        for record in records:
            if record.key.collection == "result_snapshots":
                result = load_record(ResultSnapshot, record.body)
                saved_vectors[result.id] = {
                    case.case_id: case.answer.probabilities_source
                    for case in result.results
                    if case.answer is not None
                }
        del records
    executable = Path(sys.executable).with_name("deykit.exe" if os.name == "nt" else "deykit")

    def cli(*args):
        result = subprocess.run(
            [str(executable), "--project", str(project), "--json", *args],
            text=True,
            capture_output=True,
            # Each cold CLI process validates both full cohorts and saved reports.
            timeout=600,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        envelope = json.loads(result.stdout)
        assert "error" not in envelope
        return envelope["data"]

    compare_args = (
        "compare",
        evidence["run_id"],
        evidence["right_run_id"],
        "--evaluation-a",
        evidence["evaluation_id"],
        "--evaluation-b",
        evidence["right_evaluation_id"],
        "--operation-id",
        "large-comparison",
    )
    comparison = cli(*compare_args)
    replayed = cli(*compare_args)
    assert replayed["comparison_id"] == comparison["comparison_id"]
    assert replayed["replayed"] is True
    assert replayed["outcomes"] == comparison["outcomes"]
    assert replayed["dispatch_count"] == comparison["dispatch_count"] == 0
    outcomes = comparison["outcomes"]
    assert len(outcomes["cases"]) == COUNT
    assert outcomes["quality_denominator"] == 2496
    assert {key: count for key, count in outcomes["primary_counts"].items() if count} == {
        "both_correct": 2493,
        "improved": 1,
        "regressed": 1,
        "both_wrong": 1,
        "unavailable_answer": 2,
        "excluded_expectation": 1,
        "unlabelled_agreement": 1,
    }
    report_args = (
        "report",
        "export",
        comparison["comparison_id"],
        "--target-kind",
        "comparison",
        "--preset",
        "classification",
        "--format",
        "json",
        "--operation-id",
        "large-comparison-report",
        "--output",
        str(tmp_path / "comparison.json"),
    )
    created = cli(*report_args)
    assert created["success"] is True
    report_id = created["report"]["report_id"]
    original_json = (tmp_path / "comparison.json").read_bytes()
    assert cli(*report_args)["report"]["report_id"] == report_id
    assert (tmp_path / "comparison.json").read_bytes() == original_json
    for format_name in ("markdown", "csv"):
        assert (
            cli(
                "report",
                "export",
                "--report-id",
                report_id,
                "--format",
                format_name,
                "--output",
                str(tmp_path / f"comparison.{format_name}"),
            )["success"]
            is True
        )
    exported = json.loads((tmp_path / "comparison.json").read_text())
    content = exported["content"]
    assert content["comparison"] == outcomes
    for summary in content["classification"]["evaluations"]:
        assert (
            summary["selected_count"],
            summary["applicable_count"],
            summary["excluded_count"],
        ) == (
            2500,
            2498,
            2,
        )
        assert summary["full_cohort_strict_accuracy"]["numerator"] == 2494
        assert summary["full_cohort_strict_accuracy"]["denominator"] == 2498
        assert summary["applicable_status_counts"]["response_error"] == 1
        assert summary["applicable_status_counts"]["unknown"] == 1
        assert len(summary["classes"]) == 104
        assert summary["cost"]["reason"] == "fixture_no_usage"
    for evaluation in content["evaluations"]:
        assert len(evaluation["cases"]) == len(evaluation["attempts"]) == COUNT
        expected_vectors = saved_vectors[evaluation["context"]["result_snapshot_id"]]
        for case in evaluation["cases"]:
            if case["status"] != "valid":
                continue
            assert case["probabilities_source"] == expected_vectors[case["case_id"]]
            probabilities = json.loads(case["probabilities_source"], parse_float=Decimal)
            assert set(probabilities) == {f"category-{i:03}" for i in range(104)}
            assert probabilities[case["answer_option_id"]] == Decimal("0.9872839507317331")
            assert sum(probabilities.values()) == 1
    with (tmp_path / "comparison.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 5000
    assert len({(row["evaluation_id"], row["case_id"]) for row in rows}) == 5000
    assert sum(row["strict_correct"] == "true" for row in rows) == 4988
    assert sum(row["strict_correct"] == "false" for row in rows) == 8
    assert sum(row["strict_correct"] == "" for row in rows) == 4
    assert {row["report_id"] for row in rows} == {report_id}
    assert {row["content_hash"] for row in rows} == {exported["content_hash"]}
    markdown = (tmp_path / "comparison.markdown").read_text()
    assert "2494/2498" in markdown
    sections = markdown.split("\n## ")
    case_tables = [
        section
        for section in sections
        if section.startswith(("Evaluation 1", "Evaluation 2", "Comparison\n"))
    ]
    assert len(case_tables) == 3
    for section in case_tables:
        for index in range(COUNT):
            assert section.count(f"| product-{index:04} | ") == 1
    with FileProjectSource(project) as source:
        after = {record.key: record.etag for record in source.capture_snapshot()}
    assert all(after.get(key) == etag for key, etag in before.items())
    derived = {
        ResourceKey("comparisons", comparison["comparison_id"]),
        ResourceKey("reports", report_id),
    }
    assert derived <= after.keys()
    assert after.keys() - before.keys() == derived - before.keys()
