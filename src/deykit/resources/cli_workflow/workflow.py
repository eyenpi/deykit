"""Installed-console walkthrough backed only by packaged authored resources."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

RESOURCE_PACKAGE = "deykit.resources.cli_workflow"
ORACLE: dict[str, Any] = {
    "case_count": 6,
    "initial_requests": 5,
    "statuses": {"valid": 4, "input_invalid": 1, "response_error": 1},
    "fixture_a": {
        "eligible_set_count": 3,
        "correct_set_count": 2,
        "class_confusion_matrix": [[1, 0], [1, 0]],
        "class_denominator": 2,
        "majority_baseline": "review",
        "baseline_fit_support": 3,
        "baseline_fit_excluded_acceptable_sets": 1,
        "baseline_scored_count": 3,
        "baseline_correct_count": 2,
        "class_f1": {
            "accept": {"numerator": 2, "denominator": 3},
            "review": {"numerator": 0, "denominator": 1},
            "macro": {"numerator": 1, "denominator": 3},
        },
        "baseline_accuracy": {"numerator": 2, "denominator": 3},
    },
    "fixture_b": {"eligible_set_count": 3, "correct_set_count": 3},
    "comparison": {
        "quality_denominator": 3,
        "primary_counts": {
            "both_correct": 2,
            "improved": 1,
            "regressed": 0,
            "both_wrong": 0,
            "unlabelled_agreement": 1,
            "unavailable_answer": 2,
        },
    },
    "reevaluated_a_after_c002_accept": {
        "eligible_set_count": 3,
        "correct_set_count": 3,
        "dispatch_count": 0,
    },
    "a_original_after_label_change": {"eligible_set_count": 3, "correct_set_count": 2},
    "diagnostic": {
        "distinct_orders": 2,
        "independent_cases": 2,
        "expanded_results": 4,
        "initial_requests": 4,
        "disagreements": 0,
        "unavailable": 0,
        "attempt_cap": 4,
    },
    "regression_check_v1_a": {"attempts": 1, "expectation_failures": 1, "exit_code": 5},
    "regression_check_v2_b": {"attempts": 1, "expectation_failures": 0, "exit_code": 0},
}


class Workflow:
    def __init__(self, executable: str, project: Path, output: Path, bundle: Path) -> None:
        self.executable = executable
        self.project = project
        self.output = output
        self.bundle = bundle
        self.progress_log = output / "progress.jsonl"
        self.state_path = output / "workflow-state.json"
        self.decision_id = "tutorial-choice"
        self.dataset_id = "tutorial-cases"
        self.v1_revision = ""
        self.v2_revision = ""
        self.fixture_a = "tutorial-fixture-a"
        self.fixture_b = "tutorial-fixture-b"
        self.original_only_fixture = "tutorial-fixture-b-original-only"
        self.run_a = ""
        self.run_b = ""
        self.result_a = ""
        self.result_b = ""
        self.result_snapshot_ids_a: tuple[str, ...] = ()
        self.evaluation_a = ""
        self.evaluation_b = ""
        self.evaluation_a_reevaluated = ""
        self.original_report = ""
        self.original_diagnostic_report = ""
        self.original_check_report = ""
        self.regression_id = ""
        self.diagnostic_group = ""
        self.diagnostic_snapshot = ""
        self.check_group = ""
        self.check_snapshot = ""

    def call(self, *arguments: str, expected: int = 0) -> dict[str, Any]:
        prefix = (
            ["--json"]
            if arguments and arguments[0] == "init"
            else ["--project", str(self.project), "--json"]
        )
        completed = subprocess.run(
            [self.executable, *prefix, *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = completed.stdout.splitlines()
        envelope: dict[str, Any] | None = None
        if len(lines) == 1:
            try:
                parsed = json.loads(lines[0])
                if isinstance(parsed, dict) and parsed.get("schema_version") == 1:
                    envelope = parsed
            except json.JSONDecodeError:
                envelope = None
        error = envelope.get("error") if envelope else None
        self._record_call(arguments, completed.returncode, expected, envelope)
        if completed.returncode != expected:
            safe_error = (
                f"; code={error.get('code')} reason={error.get('reason')}"
                if isinstance(error, dict)
                else ""
            )
            raise RuntimeError(
                f"command failed at {arguments[0]} (expected {expected}, "
                f"received {completed.returncode}){safe_error}; "
                f"one_line_json_envelope={envelope is not None}; "
                f"stderr_bytes={len(completed.stderr.encode('utf-8'))}"
            )
        if envelope is None:
            raise RuntimeError(f"expected one JSON envelope; got {len(lines)} lines")
        return envelope

    @staticmethod
    def _command_path(arguments: tuple[str, ...]) -> str:
        roots = {
            "case",
            "checks",
            "dataset",
            "decision",
            "diagnose",
            "fixture",
            "label",
            "project",
            "provider",
            "report",
            "regression",
            "results",
            "runs",
        }
        length = 2 if arguments and arguments[0] in roots else 1
        return " ".join(arguments[:length])

    @staticmethod
    def _safe_ids(value: Any) -> list[str]:
        found: set[str] = set()

        def visit(item: Any) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    if (key == "id" or key.endswith("_id")) and isinstance(child, str):
                        found.add(child)
                    else:
                        visit(child)
            elif isinstance(item, list):
                for child in item:
                    visit(child)

        visit(value)
        return sorted(found)

    def _record_call(
        self,
        arguments: tuple[str, ...],
        actual: int,
        expected: int,
        envelope: dict[str, Any] | None,
    ) -> None:
        entry: dict[str, Any] = {
            "command": self._command_path(arguments),
            "exit_code": actual,
            "expected_exit_code": expected,
            "ok": actual == expected,
        }
        if envelope is not None:
            if isinstance(envelope.get("data"), dict):
                entry["ids"] = self._safe_ids(envelope["data"])
            error = envelope.get("error")
            if isinstance(error, dict):
                entry["error"] = {
                    "code": error.get("code"),
                    "reason": error.get("reason"),
                }
        with self.progress_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")

    def checkpoint(self, step: str) -> None:
        identifiers = (
            "decision_id",
            "dataset_id",
            "fixture_a",
            "fixture_b",
            "original_only_fixture",
            "v1_revision",
            "v2_revision",
            "run_a",
            "run_b",
            "result_a",
            "result_b",
            "evaluation_a",
            "evaluation_b",
            "evaluation_a_reevaluated",
            "original_report",
            "original_diagnostic_report",
            "original_check_report",
            "regression_id",
            "diagnostic_group",
            "diagnostic_snapshot",
            "check_group",
            "check_snapshot",
        )
        state = {
            "completed_step": step,
            "project": str(self.project),
            "ids": {
                key: value
                for key in identifiers
                if isinstance((value := getattr(self, key)), str) and value
            },
        }
        self.state_path.write_text(
            json.dumps(state, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )

    def data(self, *arguments: str, expected: int = 0) -> dict[str, Any]:
        envelope = self.call(*arguments, expected=expected)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"expected a data outcome from {arguments[0]}")
        return cast(dict[str, Any], data)

    def resource(self, name: str) -> Path:
        return self.bundle / name

    def expect_oracle(self, observed: dict[str, Any], expected: dict[str, Any]) -> None:
        for key, value in expected.items():
            if observed.get(key) != value:
                raise RuntimeError(f"oracle mismatch for {key}: {observed.get(key)!r} != {value!r}")

    @staticmethod
    def rate(value: dict[str, Any], numerator: int, denominator: int) -> None:
        if value.get("numerator") != numerator or value.get("denominator") != denominator:
            raise RuntimeError(f"expected rate {numerator}/{denominator}, got {value!r}")

    @staticmethod
    def assert_initial_attempts(progress: dict[str, Any]) -> None:
        attempts = progress["attempts"]
        expected = ORACLE["initial_requests"]
        if (
            progress["attempts_used"] != expected
            or len(attempts) != expected
            or any(attempt["kind"] != "initial" for attempt in attempts)
        ):
            raise RuntimeError("fixture run attempts differ from the authored request count")

    def expect_choice(self, envelope: dict[str, Any], kind: str, resource_id: str) -> None:
        selection = envelope.get("selection")
        choices = selection.get("choices", []) if isinstance(selection, dict) else []
        if not any(
            choice.get("kind") == kind and choice.get("resource_id") == resource_id
            for choice in choices
        ):
            raise RuntimeError(f"missing {kind}/{resource_id} from selector choices")

    def expect_choices(
        self,
        envelope: dict[str, Any],
        expected: list[tuple[str, str, list[str]]],
    ) -> None:
        selection = envelope.get("selection")
        choices = selection.get("choices", []) if isinstance(selection, dict) else []
        actual = sorted(
            (item.get("kind"), item.get("resource_id"), item.get("scope"))
            for item in choices
            if isinstance(item, dict)
        )
        if actual != sorted(expected):
            raise RuntimeError(f"selector scope mismatch: {actual!r} != {sorted(expected)!r}")

    def prepare(self) -> None:
        self.output.mkdir(parents=True)
        self.bundle.mkdir()
        self.progress_log.write_text("", encoding="utf-8")
        resources = files(RESOURCE_PACKAGE)
        for item in resources.iterdir():
            if item.name.endswith((".json", ".jsonl")):
                (self.bundle / item.name).write_bytes(item.read_bytes())
        case_source = self.resource("cases.jsonl").read_text(encoding="utf-8")
        exact = '"amount":9007199254740993,"ratio":0.1234567890123456789'
        if exact not in case_source:
            raise RuntimeError("the authored large integer/decimal literals changed")
        for fixture_name in ("fixture-a.jsonl", "fixture-b.jsonl"):
            fixture_line = self.resource(fixture_name).read_text(encoding="utf-8").splitlines()[0]
            binding = json.loads(fixture_line)
            request_body = binding["request"]["body"]
            if exact not in request_body:
                raise RuntimeError(
                    f"{fixture_name} does not preserve the authored exact request bytes"
                )

    def step1_create_project_and_decision(self) -> None:
        self.data("init", str(self.project), "--name", "Tutorial Project")
        self.data("project", "show")
        self.data("project", "validate")
        self.data(
            "decision",
            "create",
            self.decision_id,
            "--name",
            "Tutorial choice",
            "--file",
            str(self.resource("v1-definition.json")),
        )
        self.data("decision", "validate", self.decision_id)
        saved = self.data(
            "decision", "save", self.decision_id, "--operation-id", "tutorial-save-v1"
        )
        self.v1_revision = saved["result"]["record"]["id"]
        history = self.data("decision", "history", self.decision_id)
        if history["total"] != 1 or history["items"][0]["record"]["id"] != self.v1_revision:
            raise RuntimeError("the saved v1 revision is not visible in decision history")

    def step2_import_six_cases_and_labels(self) -> None:
        self.data("dataset", "create", self.dataset_id, "--name", "Tutorial cases")
        imported = self.data(
            "dataset",
            "import",
            self.dataset_id,
            "--format",
            "jsonl",
            "--mapping",
            str(self.resource("mapping.json")),
            "--file",
            str(self.resource("cases.jsonl")),
            "--operation-id",
            "tutorial-import",
        )
        imported_ids = imported["result"]["imported_case_ids"]
        if len(imported_ids) != ORACLE["case_count"]:
            raise RuntimeError("the six authored cases were not imported")
        self.data(
            "label",
            "set",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--file",
            str(self.resource("labels-initial.json")),
            "--operation-id",
            "tutorial-labels-v1",
        )
        first = self.data("case", "list", "--dataset", self.dataset_id, "--limit", "2")
        second = self.data(
            "case",
            "list",
            "--dataset",
            self.dataset_id,
            "--limit",
            "2",
            "--cursor",
            first["next_cursor"],
        )
        if len(first["items"]) != 2 or len(second["items"]) != 2 or first["next_cursor"] is None:
            raise RuntimeError("dataset case pagination did not advance")
        listed_labels = self.data(
            "label", "list", "--decision", self.decision_id, "--dataset", self.dataset_id
        )
        labeled_case_ids = {
            item["case"]["id"] for item in listed_labels["items"] if item["label"] is not None
        }
        unlabelled_case_ids = {
            item["case"]["id"] for item in listed_labels["items"] if item["label"] is None
        }
        if (
            listed_labels["total"] != ORACLE["case_count"]
            or labeled_case_ids != {"c-001", "c-002", "c-003", "c-006"}
            or unlabelled_case_ids != {"c-004", "c-005"}
        ):
            raise RuntimeError("label listing does not distinguish authored and unlabelled cases")
        # Exercise every label transition on the separate, initially unlabelled c-004 row.
        self.data(
            "label",
            "set",
            "c-004",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--expected",
            "review",
            "--provenance",
            "human",
            "--operation-id",
            "tutorial-label-set-c004",
        )
        self.data(
            "label",
            "dispute",
            "c-004",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--reason",
            "Check the human expectation.",
            "--operation-id",
            "tutorial-label-dispute-c004",
        )
        self.data(
            "label",
            "resolve",
            "c-004",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--expected",
            "review",
            "--operation-id",
            "tutorial-label-resolve-c004",
        )
        self.data(
            "label",
            "clear",
            "c-004",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--operation-id",
            "tutorial-label-clear-c004",
        )
        self.scratch_authoring_checks()

    def scratch_authoring_checks(self) -> None:
        scratch = "tutorial-scratch-import"
        self.data("dataset", "create", scratch, "--name", "Scratch import checks")
        conflicting = self.call(
            "dataset",
            "import",
            scratch,
            "--format",
            "jsonl",
            "--mapping",
            str(self.resource("mapping.json")),
            "--file",
            str(self.resource("cases.jsonl")),
            "--stdin",
            "--decision",
            self.decision_id,
            "--revision",
            self.v1_revision,
            expected=2,
        )
        if conflicting["error"]["reason"] != "input_mode_conflict":
            raise RuntimeError("file/stdin conflict was not rejected safely")
        rejected = self.call(
            "dataset",
            "import",
            scratch,
            "--format",
            "jsonl",
            "--mapping",
            str(self.resource("mapping.json")),
            "--file",
            str(self.resource("cases-invalid-import.jsonl")),
            "--decision",
            self.decision_id,
            "--revision",
            self.v1_revision,
            "--operation-id",
            "tutorial-invalid-import-atomic",
            expected=2,
        )
        if rejected["error"]["code"] != "validation_error":
            raise RuntimeError("decision-aware invalid import was not rejected")
        unchanged = self.data("dataset", "show", scratch)
        if unchanged["cases"]["total"] != 0:
            raise RuntimeError("atomic rejected import wrote rows to its scratch dataset")
        self.data(
            "dataset",
            "import",
            scratch,
            "--format",
            "jsonl",
            "--mapping",
            str(self.resource("mapping.json")),
            "--file",
            str(self.resource("cases-invalid-import.jsonl")),
            "--decision",
            self.decision_id,
            "--revision",
            self.v1_revision,
            "--skip-invalid",
            "--operation-id",
            "tutorial-invalid-import-skip",
        )
        if self.data("dataset", "show", scratch)["cases"]["total"] != 1:
            raise RuntimeError("skip-invalid did not retain exactly the valid scratch row")
        split_dataset = "tutorial-scratch-split"
        self.data("dataset", "create", split_dataset, "--name", "Scratch split checks")
        self.data(
            "dataset",
            "import",
            split_dataset,
            "--format",
            "jsonl",
            "--mapping",
            str(self.resource("mapping.json")),
            "--file",
            str(self.resource("split-cases.jsonl")),
            "--operation-id",
            "tutorial-split-import",
        )
        self.data(
            "dataset",
            "split",
            split_dataset,
            "--seed",
            "7",
            "--development",
            "0.5",
            "--calibration",
            "0",
            "--test",
            "0.5",
            "--operation-id",
            "tutorial-split",
        )
        self.data("dataset", "create", "tutorial-archive", "--name", "Archive restore check")
        self.data("dataset", "archive", "tutorial-archive", "--operation-id", "tutorial-archive")
        self.data("dataset", "restore", "tutorial-archive", "--operation-id", "tutorial-restore")

    def step3_author_fixture_a_and_run(self) -> None:
        created = self.data(
            "fixture",
            "create",
            self.fixture_a,
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--name",
            "Authored fixture A",
            "--model",
            "authored-tutorial-a-v1",
            "--file",
            str(self.resource("fixture-a.jsonl")),
            "--operation-id",
            "tutorial-fixture-a",
        )
        if created["dispatch_count"] != 0 or created["replayed"]:
            raise RuntimeError("fixture authoring dispatched or unexpectedly replayed")
        default_summary = self.data("fixture", "show", self.fixture_a)
        if default_summary["requests"]:
            raise RuntimeError("fixture show exposed raw requests by default")
        requested_summary = self.data("fixture", "show", self.fixture_a, "--request")
        if len(requested_summary["requests"]) != 5:
            raise RuntimeError("fixture show --request did not expose the authored bodies")
        missing_case_source = self.resource("fixture-a.jsonl").read_text(encoding="utf-8")
        first_binding = missing_case_source.splitlines()[0]
        missing_case_binding = first_binding.replace(
            '"case_id":"c-001"', '"case_id":"missing-fixture-case"'
        )
        if missing_case_binding == first_binding:
            raise RuntimeError("could not author the missing fixture binding selector")
        missing_case_file = self.output / "fixture-missing-case.jsonl"
        missing_case_file.write_text(missing_case_binding + "\n", encoding="utf-8")
        missing_fixture_case = self.call(
            "fixture",
            "create",
            "tutorial-fixture-missing-case",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--name",
            "Missing case selector probe",
            "--model",
            "authored-tutorial-a-v1",
            "--file",
            str(missing_case_file),
            "--operation-id",
            "tutorial-fixture-missing-case",
            expected=2,
        )
        self.expect_choices(
            missing_fixture_case,
            [
                ("case", case_id, [self.dataset_id])
                for case_id in (
                    "c-001",
                    "c-002",
                    "c-003",
                    "c-004",
                    "c-005",
                    "c-006",
                )
            ],
        )
        self.data(
            "fixture",
            "create",
            self.fixture_a,
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--name",
            "Authored fixture A",
            "--model",
            "authored-tutorial-a-v1",
            "--file",
            str(self.resource("fixture-a.jsonl")),
            "--operation-id",
            "tutorial-fixture-a",
        )
        before = self.data("runs", "list")["total"]
        preview = self.data(
            "run",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_a,
            "--revision",
            self.v1_revision,
            "--attempt-limit",
            "5",
            "--dry-run",
        )
        if preview["initial_requests"] != ORACLE["initial_requests"]:
            raise RuntimeError("dry-run request count differs from the authored oracle")
        if self.data("runs", "list")["total"] != before:
            raise RuntimeError("dry-run created a run")
        args = (
            "run",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_a,
            "--revision",
            self.v1_revision,
            "--attempt-limit",
            "5",
            "--operation-id",
            "tutorial-run-a",
        )
        run = self.data(*args, expected=3)
        progress = run["run"]
        self.run_a = progress["run_id"]
        self.result_a = progress["latest_result_snapshot_id"]
        self.result_snapshot_ids_a = tuple(progress["result_snapshot_ids"])
        if self.result_a not in self.result_snapshot_ids_a:
            raise RuntimeError("latest result snapshot is absent from the public run history")
        self.evaluation_a = run["evaluation_id"]
        statuses = {status: 0 for status in ("valid", "input_invalid", "response_error")}
        self.assert_initial_attempts(progress)
        for case in progress["cases"]:
            statuses[case["status"]] = statuses.get(case["status"], 0) + 1
        if statuses != ORACLE["statuses"]:
            raise RuntimeError(f"fixture A statuses differ from oracle: {statuses!r}")
        replay = self.data(*args, expected=3)
        if replay["run"]["run_id"] != self.run_a or not replay["run"]["replayed"]:
            raise RuntimeError("run operation replay did not return its original identity")
        missing_dataset = self.call("dataset", "show", "missing-dataset", expected=2)
        self.expect_choice(missing_dataset, "dataset", self.dataset_id)
        missing_fixture = self.call("fixture", "show", "missing-fixture", expected=2)
        self.expect_choice(missing_fixture, "fixture", self.fixture_a)
        missing_run = self.call("runs", "show", "missing-run", expected=2)
        self.expect_choice(missing_run, "run", self.run_a)
        missing_evaluation = self.call(
            "results", "list", self.run_a, "--evaluation", "missing-evaluation", expected=2
        )
        self.expect_choice(missing_evaluation, "evaluation", self.evaluation_a)
        missing_snapshot = self.call(
            "reevaluate",
            self.run_a,
            "--result-snapshot",
            "missing-result-snapshot",
            "--operation-id",
            "tutorial-missing-result-snapshot",
            expected=2,
        )
        self.expect_choice(missing_snapshot, "result_snapshot", self.result_a)
        missing_implicit_report_snapshot = self.call(
            "report",
            "export",
            self.run_a,
            "--result-snapshot",
            "missing-report-result",
            "--format",
            "json",
            "--output",
            str(self.output / "missing-run-report.json"),
            "--operation-id",
            "tutorial-missing-run-report-snapshot",
            expected=2,
        )
        self.expect_choices(
            missing_implicit_report_snapshot,
            [("result_snapshot", snapshot_id, []) for snapshot_id in self.result_snapshot_ids_a],
        )
        missing_implicit_report_evaluation = self.call(
            "report",
            "export",
            self.run_a,
            "--evaluation",
            "missing-report-evaluation",
            "--format",
            "json",
            "--output",
            str(self.output / "missing-run-report-evaluation.json"),
            "--operation-id",
            "tutorial-missing-run-report-evaluation",
            expected=2,
        )
        self.expect_choices(
            missing_implicit_report_evaluation,
            [("evaluation", self.evaluation_a, [])],
        )
        wrong_regression_case = self.call(
            "regression",
            "add",
            self.run_a,
            "scratch-split-1",
            "--expected",
            "review",
            "--reason",
            "This case belongs to another dataset.",
            expected=2,
        )
        self.expect_choices(
            wrong_regression_case,
            [
                ("case", case_id, [self.dataset_id])
                for case_id in (
                    "c-001",
                    "c-002",
                    "c-003",
                    "c-004",
                    "c-005",
                    "c-006",
                )
            ],
        )
        results = self.data("results", "list", self.run_a, "--evaluation", self.evaluation_a)
        summary = results["summary"]
        self.rate(summary["set_accuracy"], 2, 3)
        if (
            summary["eligible_set_count"] != ORACLE["fixture_a"]["eligible_set_count"]
            or summary["correct_set_count"] != ORACLE["fixture_a"]["correct_set_count"]
        ):
            raise RuntimeError("fixture A eligible/correct counts differ from oracle")
        if summary["confusion_matrix"] != [[1, 0], [1, 0]]:
            raise RuntimeError("fixture A class confusion matrix differs from oracle")
        self.data(
            "results",
            "annotate",
            self.run_a,
            "c-004",
            "--note",
            "Reviewed in the CLI walkthrough.",
            "--operation-id",
            "tutorial-note-a-c004",
        )
        request_detail = self.data("results", "show", self.run_a, "c-001", "--request")
        rendered = json.dumps(request_detail, sort_keys=True, separators=(",", ":"))
        if "9007199254740993" not in rendered or "0.1234567890123456789" not in rendered:
            raise RuntimeError("exact input numerics did not reach the prepared request")
        self.export_run_report()

    def export_run_report(self) -> None:
        destination = self.output / "run-a.md"
        exported = self.data(
            "report",
            "export",
            self.run_a,
            "--target-kind",
            "run",
            "--evaluation",
            self.evaluation_a,
            "--result-snapshot",
            self.result_a,
            "--format",
            "markdown",
            "--output",
            str(destination),
            "--operation-id",
            "tutorial-report-a",
        )
        self.original_report = exported["report"]["report_id"]
        if exported["report"]["raw"] != {"inputs": False, "requests": False, "responses": False}:
            raise RuntimeError("new reports do not default to raw bodies off")
        if not destination.is_file():
            raise RuntimeError("the run report was not exported")
        for flag, expected_key in (
            ("--include-raw-inputs", "inputs"),
            ("--include-raw-requests", "requests"),
            ("--include-raw-responses", "responses"),
        ):
            raw_path = self.output / f"raw-{expected_key}.md"
            raw = self.data(
                "report",
                "export",
                self.run_a,
                "--target-kind",
                "run",
                "--evaluation",
                self.evaluation_a,
                "--result-snapshot",
                self.result_a,
                flag,
                "--format",
                "markdown",
                "--output",
                str(raw_path),
                "--operation-id",
                f"tutorial-report-a-raw-{expected_key}",
            )
            if raw["report"]["raw"][expected_key] is not True:
                raise RuntimeError(f"{flag} did not set only its declared report choice")
            if sum(raw["report"]["raw"].values()) != 1:
                raise RuntimeError(f"{flag} changed another raw report choice")
        report_json_path = self.output / "run-a.json"
        self.data(
            "report",
            "export",
            "--report-id",
            self.original_report,
            "--format",
            "json",
            "--output",
            str(report_json_path),
        )
        report_json = json.loads(report_json_path.read_text(encoding="utf-8"))
        metrics = report_json["content"]["evaluations"][0]["metrics"]
        summary = metrics["summary"]
        class_metrics = {item["option_id"]: item for item in summary["classes"]}
        for class_id in ("accept", "review"):
            expected = ORACLE["fixture_a"]["class_f1"][class_id]
            self.rate(class_metrics[class_id]["f1"], expected["numerator"], expected["denominator"])
        self.rate(summary["macro_f1"], 1, 3)
        baseline = metrics["baseline"]
        if (
            baseline["option_id"] != "review"
            or baseline["fit_support"] != 3
            or baseline["fit_excluded_acceptable_sets"] != 1
            or baseline["scored_count"] != 3
            or baseline["overlap_case_ids"] != ["c-001", "c-002"]
            or summary["single_label_count"] != 2
            or summary["macro_f1_class_count"] != 2
        ):
            raise RuntimeError("fixture A majority baseline differs from independent oracle")
        self.rate(baseline["accuracy"], 2, 3)
        if (
            metrics["usage"]["reason"] != "fixture_no_usage"
            or metrics["usage"]["total_input_tokens"] is not None
            or metrics["usage"]["total_output_tokens"] is not None
            or metrics["latency"]["reason"] != "fixture_has_no_live_latency"
            or metrics["latency"]["sample_count"] != 0
        ):
            raise RuntimeError("fixture report invented usage or live latency")

    def step4_revision_b_and_compare(self) -> None:
        self.data(
            "decision",
            "edit",
            self.decision_id,
            "--file",
            str(self.resource("v2-definition.json")),
            "--operation-id",
            "tutorial-edit-v2",
        )
        saved = self.data(
            "decision", "save", self.decision_id, "--operation-id", "tutorial-save-v2"
        )
        self.v2_revision = saved["result"]["record"]["id"]
        self.data(
            "fixture",
            "create",
            self.fixture_b,
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--name",
            "Authored fixture B",
            "--model",
            "authored-tutorial-b-v2",
            "--file",
            str(self.resource("fixture-b.jsonl")),
            "--operation-id",
            "tutorial-fixture-b",
        )
        first = self.data("fixture", "list", "--limit", "1")
        second = self.data("fixture", "list", "--limit", "1", "--cursor", first["next_cursor"])
        if first["next_cursor"] is None or first["total"] < 2 or len(second["items"]) != 1:
            raise RuntimeError("fixture listing did not paginate deterministically")
        args = (
            "run",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--attempt-limit",
            "5",
            "--operation-id",
            "tutorial-run-b",
        )
        run = self.data(*args, expected=3)
        progress = run["run"]
        self.run_b = progress["run_id"]
        self.result_b = progress["latest_result_snapshot_id"]
        self.evaluation_b = run["evaluation_id"]
        statuses = {status: 0 for status in ("valid", "input_invalid", "response_error")}
        self.assert_initial_attempts(progress)
        for case in progress["cases"]:
            statuses[case["status"]] = statuses.get(case["status"], 0) + 1
        if statuses != ORACLE["statuses"]:
            raise RuntimeError("fixture B request or status counts differ from oracle")
        results = self.data("results", "list", self.run_b, "--evaluation", self.evaluation_b)
        if (
            results["summary"]["eligible_set_count"] != ORACLE["fixture_b"]["eligible_set_count"]
            or results["summary"]["correct_set_count"] != ORACLE["fixture_b"]["correct_set_count"]
        ):
            raise RuntimeError("fixture B eligible/correct counts differ from oracle")
        self.rate(results["summary"]["set_accuracy"], 3, 3)
        wrong_owner_evaluation = self.call(
            "compare",
            self.run_a,
            self.run_b,
            "--evaluation-a",
            self.evaluation_b,
            expected=2,
        )
        self.expect_choices(
            wrong_owner_evaluation,
            [("evaluation", self.evaluation_a, [])],
        )
        comparison = self.data(
            "compare",
            self.run_a,
            self.run_b,
            "--evaluation-a",
            self.evaluation_a,
            "--evaluation-b",
            self.evaluation_b,
            "--operation-id",
            "tutorial-comparison-ab",
        )
        outcomes = comparison["outcomes"]
        if outcomes["quality_denominator"] != 3:
            raise RuntimeError("comparison quality denominator differs from oracle")
        for key, value in ORACLE["comparison"]["primary_counts"].items():
            if outcomes["primary_counts"][key] != value:
                raise RuntimeError(f"comparison count {key} differs from oracle")

    def step5_zero_call_reevaluation(self) -> None:
        report_bytes = (self.output / "run-a.md").read_bytes()
        self.data(
            "label",
            "set",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--file",
            str(self.resource("labels-revision.json")),
            "--operation-id",
            "tutorial-label-c002-accept",
        )
        evaluated = self.data(
            "reevaluate",
            self.run_a,
            "--result-snapshot",
            self.result_a,
            "--operation-id",
            "tutorial-reevaluate-a",
        )
        metrics = evaluated["metrics"]
        self.evaluation_a_reevaluated = evaluated["evaluation_id"]
        summary = metrics["summary"]
        self.expect_oracle(
            {
                "eligible_set_count": summary["eligible_set_count"],
                "correct_set_count": summary["correct_set_count"],
                "dispatch_count": evaluated["dispatch_count"],
            },
            ORACLE["reevaluated_a_after_c002_accept"],
        )
        baseline = metrics["baseline"]
        if baseline["option_id"] != "review" or baseline["fit_support"] != 3:
            raise RuntimeError("reevaluation changed the original baseline fit")
        self.rate(baseline["accuracy"], 1, 3)
        initial_report = json.loads((self.output / "run-a.json").read_text(encoding="utf-8"))
        initial_metrics = initial_report["content"]["evaluations"][0]["metrics"]
        initial_baseline = initial_metrics["baseline"]
        if (
            evaluated["label_snapshot_id"] == initial_metrics["label_snapshot_id"]
            or baseline["fit_label_snapshot_id"] != initial_baseline["fit_label_snapshot_id"]
            or baseline["fit_dataset_snapshot_id"] != initial_baseline["fit_dataset_snapshot_id"]
        ):
            raise RuntimeError(
                "reevaluation did not freeze a new label snapshot over prior fit data"
            )
        label_comparison = self.data(
            "compare",
            self.run_a,
            self.run_a,
            "--evaluation-a",
            self.evaluation_a,
            "--evaluation-b",
            self.evaluation_a_reevaluated,
            "--operation-id",
            "tutorial-comparison-label-revision",
        )["outcomes"]
        if (
            label_comparison["primary_counts"]["changed_expectations"] != 1
            or label_comparison["quality_denominator"] != 2
            or label_comparison["primary_counts"]["both_correct"] != 2
            or label_comparison["primary_counts"]["unlabelled_agreement"] != 1
            or label_comparison["primary_counts"]["unavailable_answer"] != 2
        ):
            raise RuntimeError("same-run reevaluation comparison differs from independent oracle")
        original = self.data("results", "list", self.run_a, "--evaluation", self.evaluation_a)
        self.rate(original["summary"]["set_accuracy"], 2, 3)
        reexport = self.output / "run-a-reexport.md"
        self.data(
            "report",
            "export",
            "--report-id",
            self.original_report,
            "--format",
            "markdown",
            "--output",
            str(reexport),
        )
        if reexport.read_bytes() != report_bytes:
            raise RuntimeError("saved report bytes changed after current label edits")

    def step6_frozen_regression_checks(self) -> None:
        self.data(
            "label",
            "set",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--file",
            str(self.resource("labels-restored.json")),
            "--operation-id",
            "tutorial-label-c002-review",
        )
        added = self.data(
            "regression",
            "add",
            self.run_a,
            "c-002",
            "--expected",
            "review",
            "--reason",
            "The v1 fixture A answer for this original input is incorrect.",
            "--result-snapshot",
            self.result_a,
            "--operation-id",
            "tutorial-regression-c002",
        )
        self.regression_id = added["result"]["id"]
        missing_regression = self.call(
            "regression",
            "remove",
            "missing-regression",
            "--decision",
            self.decision_id,
            expected=2,
        )
        self.expect_choice(missing_regression, "regression", self.regression_id)
        failed = self.data(
            "check",
            "--decision",
            self.decision_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_a,
            "--revision",
            self.v1_revision,
            "--regression",
            self.regression_id,
            "--attempt-limit",
            "1",
            "--operation-id",
            "tutorial-check-v1-a",
            expected=5,
        )
        group = failed["group"]
        self.check_group = group["group_id"]
        self.check_snapshot = group["snapshot_id"]
        self.expect_oracle(
            {
                "attempts": group["attempts_used"],
                "expectation_failures": failed["expectation_failures"],
            },
            ORACLE["regression_check_v1_a"],
        )
        passed = self.data(
            "check",
            "--decision",
            self.decision_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--regression",
            self.regression_id,
            "--attempt-limit",
            "1",
            "--operation-id",
            "tutorial-check-v2-b",
        )
        self.expect_oracle(
            {
                "attempts": passed["group"]["attempts_used"],
                "expectation_failures": passed["expectation_failures"],
                "exit_code": 0,
            },
            ORACLE["regression_check_v2_b"],
        )
        self.check_group = passed["group"]["group_id"]
        self.check_snapshot = passed["group"]["snapshot_id"]

    def step7_order_diagnostic(self) -> None:
        args = (
            "diagnose",
            "choice-order",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--case",
            "c-001",
            "--case",
            "c-002",
            "--orders",
            "4",
            "--attempt-limit",
            "4",
            "--operation-id",
            "tutorial-order-diagnostic",
        )
        diagnostic = self.data(*args)
        group = diagnostic["group"]
        self.diagnostic_group = group["group_id"]
        self.diagnostic_snapshot = group["snapshot_id"]
        summary = diagnostic["summary"]
        self.expect_oracle(
            {
                "distinct_orders": summary["order_count"],
                "independent_cases": summary["independent_case_count"],
                "expanded_results": summary["expanded_result_count"],
                "initial_requests": group["initial_requests"],
                "disagreements": summary["disagreement"]["numerator"],
                "unavailable": sum(not case["fully_observed"] for case in summary["cases"]),
                "attempt_cap": group["attempt_limit"],
            },
            ORACLE["diagnostic"],
        )
        before = self.data("runs", "list")["total"]
        rejected = self.call(
            "diagnose",
            "choice-order",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--case",
            "c-001",
            "--case",
            "c-002",
            "--orders",
            "4",
            "--attempt-limit",
            "3",
            "--operation-id",
            "tutorial-order-cap-reject",
            expected=2,
        )
        if rejected["error"]["code"] not in {"preflight_failed", "validation_error"}:
            raise RuntimeError("diagnostic under-cap failure was not a safe preflight rejection")
        if self.data("runs", "list")["total"] != before:
            raise RuntimeError("diagnostic cap rejection created child runs")
        self.data(
            "fixture",
            "create",
            self.original_only_fixture,
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--name",
            "Original-order-only authored fixture",
            "--model",
            "authored-tutorial-b-v2",
            "--file",
            str(self.resource("fixture-b-original-only.jsonl")),
            "--operation-id",
            "tutorial-fixture-b-original-only",
        )
        partial = self.data(
            "diagnose",
            "choice-order",
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.original_only_fixture,
            "--revision",
            self.v2_revision,
            "--case",
            "c-001",
            "--case",
            "c-002",
            "--orders",
            "2",
            "--attempt-limit",
            "4",
            "--operation-id",
            "tutorial-order-original-only",
            expected=3,
        )
        if not any(not item["fully_observed"] for item in partial["summary"]["cases"]):
            raise RuntimeError("original-order-only fixtures hid reversed-order unavailability")

    def step8_pin_historical_reports_and_remove_case(self) -> None:
        diagnostic_path = self.output / "diagnostic.json"
        diagnostic_export = self.data(
            "report",
            "export",
            self.diagnostic_group,
            "--target-kind",
            "diagnostic",
            "--group-snapshot",
            self.diagnostic_snapshot,
            "--format",
            "json",
            "--output",
            str(diagnostic_path),
            "--operation-id",
            "tutorial-diagnostic-report",
        )
        self.original_diagnostic_report = diagnostic_export["report"]["report_id"]
        missing_group_snapshot = self.call(
            "report",
            "export",
            self.diagnostic_group,
            "--target-kind",
            "diagnostic",
            "--group-snapshot",
            "missing-diagnostic-snapshot",
            "--format",
            "json",
            "--output",
            str(self.output / "missing-diagnostic.json"),
            "--operation-id",
            "tutorial-missing-diagnostic-snapshot",
            expected=2,
        )
        self.expect_choices(
            missing_group_snapshot,
            [("diagnostic_snapshot", self.diagnostic_snapshot, [])],
        )
        check_path = self.output / "check.json"
        check_export = self.data(
            "report",
            "export",
            self.check_group,
            "--target-kind",
            "check",
            "--group-snapshot",
            self.check_snapshot,
            "--format",
            "json",
            "--output",
            str(check_path),
            "--operation-id",
            "tutorial-check-report",
        )
        self.original_check_report = check_export["report"]["report_id"]
        case = self.data("case", "show", "c-002", "--dataset", self.dataset_id)["record"]
        case_input_source = case["input_source"].replace(
            "Please review this request.", "Edited current case only."
        )
        if case_input_source == case["input_source"]:
            raise RuntimeError("the current c-002 text did not match the authored case")
        case_input = {
            "input_kind": case["input_kind"],
            "input_source": case_input_source,
            "tags": case["tags"],
            "split": case["split"],
            "group_id": case["group_id"],
            "derived_from": case["derived_from"],
            "metadata_source": case["metadata_source"],
        }
        replacement = self.output / "case-c002.json"
        replacement.write_text(json.dumps(case_input, separators=(",", ":")), encoding="utf-8")
        self.data(
            "case",
            "edit",
            "c-002",
            "--dataset",
            self.dataset_id,
            "--file",
            str(replacement),
            "--operation-id",
            "tutorial-edit-c002",
        )
        self.data(
            "check",
            "--decision",
            self.decision_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--regression",
            self.regression_id,
            "--attempt-limit",
            "1",
            "--operation-id",
            "tutorial-check-after-case-edit",
        )
        self.data(
            "case",
            "remove",
            "c-002",
            "--dataset",
            self.dataset_id,
            "--operation-id",
            "tutorial-remove-c002",
        )
        replayed_fixture = self.data(
            "fixture",
            "create",
            self.original_only_fixture,
            "--decision",
            self.decision_id,
            "--dataset",
            self.dataset_id,
            "--name",
            "Original-order-only authored fixture",
            "--model",
            "authored-tutorial-b-v2",
            "--file",
            str(self.resource("fixture-b-original-only.jsonl")),
            "--operation-id",
            "tutorial-fixture-b-original-only",
        )
        if not replayed_fixture["replayed"]:
            raise RuntimeError("fixture replay did not survive removal of a current binding case")
        frozen_after_delete = self.data(
            "check",
            "--decision",
            self.decision_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--regression",
            self.regression_id,
            "--attempt-limit",
            "1",
            "--operation-id",
            "tutorial-check-after-case-delete",
        )
        if frozen_after_delete["expectation_failures"] != 0:
            raise RuntimeError("frozen check changed after deleting its current case")
        self.data(
            "regression",
            "remove",
            self.regression_id,
            "--decision",
            self.decision_id,
            "--operation-id",
            "tutorial-remove-regression",
        )
        hidden_regression = self.call(
            "check",
            "--decision",
            self.decision_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--regression",
            self.regression_id,
            "--attempt-limit",
            "1",
            expected=2,
        )
        if hidden_regression["error"]["code"] != "preflight_failed":
            raise RuntimeError("a removed regression remained executable")
        self.expect_choices(hidden_regression, [])
        empty = self.call(
            "check",
            "--decision",
            self.decision_id,
            "--mode",
            "fixture",
            "--fixture-set",
            self.fixture_b,
            "--revision",
            self.v2_revision,
            "--attempt-limit",
            "1",
            expected=2,
        )
        if empty["error"]["code"] != "preflight_failed":
            raise RuntimeError("empty default regression check did not fail preflight")
        self.data("project", "validate")
        self.data("project", "rebuild-index")
        self.data("project", "validate")
        historical = self.data("results", "show", self.run_a, "c-002", "--request")
        if "Please review this request." not in json.dumps(historical, ensure_ascii=False):
            raise RuntimeError("historical result input changed with the current case")
        missing_historical_case = self.call(
            "results", "show", self.run_a, "missing-case", expected=2
        )
        self.expect_choices(
            missing_historical_case,
            [
                ("case", case_id, [self.dataset_id])
                for case_id in ("c-001", "c-002", "c-003", "c-004", "c-005", "c-006")
            ],
        )
        for report_id, filename, original_name in (
            (self.original_diagnostic_report, "diagnostic-reexport.json", "diagnostic.json"),
            (self.original_check_report, "check-reexport.json", "check.json"),
        ):
            reexport = self.output / filename
            self.data(
                "report",
                "export",
                "--report-id",
                report_id,
                "--format",
                "json",
                "--output",
                str(reexport),
            )
            if reexport.read_bytes() != (self.output / original_name).read_bytes():
                raise RuntimeError(f"historical {filename} bytes changed")
        if not diagnostic_path.is_file() or not check_path.is_file():
            raise RuntimeError("pinned group reports were not preserved")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the installed Deykit CLI tutorial.")
    parser.add_argument(
        "--cli", default=shutil.which("deykit"), help="Installed deykit executable."
    )
    parser.add_argument("--output", type=Path, required=True, help="New external output directory.")
    args = parser.parse_args()
    if not args.cli:
        parser.error("deykit executable was not found; pass --cli PATH")
    output = args.output.absolute()
    if output.exists():
        parser.error("output directory must not already exist")
    project = output / "Tutorial project ü with spaces"
    bundle = output / "authored resources"
    workflow = Workflow(args.cli, project, output, bundle)
    workflow.prepare()
    steps = (
        ("project-and-decision", workflow.step1_create_project_and_decision),
        ("six-cases-and-labels", workflow.step2_import_six_cases_and_labels),
        ("fixture-a-run-and-report", workflow.step3_author_fixture_a_and_run),
        ("fixture-b-and-comparison", workflow.step4_revision_b_and_compare),
        ("zero-call-reevaluation", workflow.step5_zero_call_reevaluation),
        ("frozen-regression-checks", workflow.step6_frozen_regression_checks),
        ("bounded-order-diagnostic", workflow.step7_order_diagnostic),
        (
            "historical-reports-and-current-case",
            workflow.step8_pin_historical_reports_and_remove_case,
        ),
    )
    for name, step in steps:
        step()
        workflow.checkpoint(name)
    print(json.dumps({"status": "complete", "project": str(project), "oracle": ORACLE}))


if __name__ == "__main__":
    main()
