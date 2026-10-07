"""Actual installed CLI failures for the original project-reference gaps."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import JsonDocument
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    ComparisonRecord,
    DatasetRecord,
    DecisionDraft,
    DecisionRecord,
    EvaluationRecord,
    LabelRecord,
    ProjectRecord,
    RegressionRecord,
    ReportRecord,
)
from deykit.domain.label_identity import label_id
from deykit.storage import FileProjectSource


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("deykit")
    return subprocess.run(
        [str(executable), *args],
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _init_project(path: Path) -> None:
    result = _cli("--json", "init", str(path), "--name", "M05 reference probe")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1


def _change(collection: str, value: Record, scope: tuple[str, ...] = ()) -> SourceChange:
    resource_id = getattr(value, "decision_id" if collection == "drafts" else "id")
    return SourceChange(
        ResourceKey(collection, resource_id, scope), dump_record(value), None
    )


def _seed(path: Path, *changes: SourceChange) -> None:
    with FileProjectSource(path) as source:
        source.commit("seed-reference-probe", tuple(changes))


def _base_decision(
    latest_revision_id: str | None = "missing-revision",
) -> tuple[SourceChange, SourceChange]:
    decision = DecisionRecord(
        id="decision", name="Decision", latest_revision_id=latest_revision_id
    )
    draft = DecisionDraft(
        decision_id="decision", editor_source="{", updated_at="2026-10-05T12:00:00Z"
    )
    return _change("decisions", decision), _change("drafts", draft)


def _probe(path: Path, name: str) -> None:
    _init_project(path)
    if name == "dangling_latest_revision":
        _seed(path, *_base_decision())
    elif name == "orphan_label":
        decision, draft = _base_decision(latest_revision_id=None)
        dataset = DatasetRecord(id="dataset", name="Data", created_at="2026-10-05T12:00:00Z")
        case_id = "missing-case"
        label = LabelRecord(
            id=label_id(case_id, "q"),
            decision_id="decision",
            dataset_id="dataset",
            case_id=case_id,
            question_id="q",
            input_hash=JsonDocument("{}").content_hash,
            acceptable_option_ids=("yes",),
            provenance="human",
            updated_at="2026-10-05T12:00:00Z",
        )
        _seed(
            path,
            decision,
            draft,
            _change("datasets", dataset),
            _change("labels", label, ("decision", "dataset")),
        )
    elif name == "dangling_evaluation":
        evaluation = EvaluationRecord(
            id="evaluation",
            run_id="missing-run",
            result_snapshot_id="missing-result",
            label_snapshot_id="missing-label",
            mode="original",
            metrics_source="{}",
            content_hash="0" * 64,
            created_at="2026-10-05T12:00:00Z",
        )
        _seed(path, _change("evaluations", evaluation))
    elif name == "dangling_comparison":
        comparison = ComparisonRecord(
            id="comparison",
            left_evaluation_id="missing-evaluation",
            right_evaluation_id="missing-evaluation",
            left_result_snapshot_id="missing-result",
            right_result_snapshot_id="missing-result",
            outcomes_source="{}",
            content_hash="0" * 64,
            created_at="2026-10-05T12:00:00Z",
        )
        _seed(path, _change("comparisons", comparison))
    elif name == "dangling_regression_revision":
        dataset = DatasetRecord(id="dataset", name="Data", created_at="2026-10-05T12:00:00Z")
        regression = RegressionRecord(
            id="regression",
            decision_revision_id="missing-revision",
            dataset_id="dataset",
            case_id="removed-case",
            question_id="q",
            input_source="{}",
            input_hash=JsonDocument("{}").content_hash,
            acceptable_option_ids=("yes",),
            reason="Retained expectation",
            created_at="2026-10-05T12:00:00Z",
        )
        _seed(path, _change("datasets", dataset), _change("regressions", regression))
    elif name == "dangling_report":
        report = ReportRecord(
            id="report",
            evaluation_ids=("missing-evaluation",),
            result_snapshot_ids=(),
            label_snapshot_ids=(),
            content_source="{}",
            content_hash="0" * 64,
            created_at="2026-10-05T12:00:00Z",
        )
        _seed(path, _change("reports", report))
    else:
        raise AssertionError(name)


@pytest.mark.parametrize(
    "name",
    [
        "dangling_latest_revision",
        "orphan_label",
        "dangling_evaluation",
        "dangling_comparison",
        "dangling_regression_revision",
        "dangling_report",
    ],
)
def test_installed_project_validate_rejects_each_original_reference_gap(
    tmp_path: Path, name: str
) -> None:
    project = tmp_path / f"{name} project"
    _probe(project, name)

    result = _cli("--json", "--project", str(project), "project", "validate")

    assert result.returncode == 2, result.stderr
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["error"]["reason"] == "project_reference_missing"


def _project_bytes(path: Path) -> dict[Path, bytes]:
    return {
        item.relative_to(path): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file() and ".deykit" not in item.relative_to(path).parts
    }


@pytest.mark.parametrize(
    ("environment_name", "destination_name"),
    [
        ("DEYKIT_TEST_REPORT_PROJECT", "cached core"),
        ("DEYKIT_TEST_REPORT_GROUP_PROJECT", "cached group"),
    ],
)
def test_cached_full_graph_validates_without_source_byte_changes(
    tmp_path: Path, environment_name: str, destination_name: str
) -> None:
    cached = os.environ.get(environment_name)
    if cached is None or not Path(cached).is_dir():
        pytest.skip(f"set {environment_name} to run cached full-graph qualification")
    destination = tmp_path / destination_name
    shutil.copytree(Path(cached), destination, ignore=shutil.ignore_patterns(".deykit"))
    before = _project_bytes(destination)

    result = _cli("--json", "--project", str(destination), "project", "validate")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["warnings"] == []
    assert _project_bytes(destination) == before
