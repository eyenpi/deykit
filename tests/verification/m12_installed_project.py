"""Offline setup and stopped/read-only byte witnesses for installed M12 qualification.

This helper runs with the clean installed interpreter, outside the checkout. It
does not fabricate execution records or call a backend. Raw report bytes go only
to owner-assigned private files; stdout never contains project evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from deykit.application.demo import read_sandbox_corpus
from deykit.application.fixtures import FixtureService
from deykit.application.reports import ReportService
from deykit.application.results import ResultInspection
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import (
    EvaluationRecord,
    FixtureBinding,
    FixtureSet,
    NormalizedAnswer,
    RunManifest,
)
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import Planner, RunRequest
from deykit.storage import FileProjectSource


class SetupClock:
    def utc_now(self) -> str:
        return "2026-10-11T12:00:00Z"

    def monotonic(self) -> float:
        raise RuntimeError("qualification_setup_forbids_execution_clock")


ORIGINAL_ORDER = ("question", "report", "request", "other")
MIN_SEED_ALTERNATE = ("other", "question", "request", "report")
MAX_SEED_ALTERNATE = ("report", "other", "request", "question")


def write_private(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)


def write_metadata(path: Path, value: dict[str, object]) -> None:
    write_private(path, (json.dumps(value, sort_keys=True) + "\n").encode())


def prepare(project: Path, workflow: str, output: Path) -> None:
    clock = SetupClock()
    corpus = read_sandbox_corpus()
    with FileProjectSource(project) as source:
        before = source.capture_snapshot()
        evaluations = source.list_ids("evaluations")
        candidates = []
        for resource_id in evaluations:
            stored = source.read(ResourceKey("evaluations", resource_id))
            if stored is None:
                raise RuntimeError("qualification_baseline_evaluation_missing")
            candidate = load_record(EvaluationRecord, stored.body)
            if candidate.mode == "original":
                candidates.append(candidate)
        if not candidates:
            raise RuntimeError("qualification_baseline_original_missing")
        admitted = []
        for candidate in candidates:
            page = ResultInspection(source).list(candidate.run_id, evaluation_id=candidate.id)
            run_record = source.read(ResourceKey("runs", candidate.run_id))
            if run_record is None:
                raise RuntimeError("qualification_baseline_run_missing")
            run = load_record(RunManifest, run_record.body)
            if (
                run.fixture_set_id == corpus.fixture_set_id
                and page.selected_count == 12
                and page.status_counts
                == {
                    "pending": 0,
                    "valid": 10,
                    "input_invalid": 1,
                    "response_error": 1,
                    "unknown": 0,
                }
                and page.summary.get("eligible_set_count") == 8
                and page.summary.get("correct_set_count") == 6
                and page.summary.get("unlabelled_valid_count") == 2
            ):
                admitted.append(candidate)
        if len(admitted) != 1:
            raise RuntimeError("qualification_baseline_not_unique_or_incomplete")
        baseline = admitted[0]
        stored_fixture = source.read(ResourceKey("fixtures", corpus.fixture_set_id))
        if stored_fixture is None:
            raise RuntimeError("qualification_authored_fixture_missing")
        original = load_record(FixtureSet, stored_fixture.body)
        selected_fixture = original.id
        prepared_count = 0
        if workflow == "C":
            bindings = tuple(
                binding.model_copy(
                    update={
                        "answer": NormalizedAnswer(
                            question_id="category",
                            option_id="question",
                            reported_model=corpus.model_identity,
                        )
                    }
                )
                if binding.case_id == "ex-003"
                else binding
                for binding in original.bindings
            )
            selected_fixture = "m12-comparison-authored"
            FixtureService(source, clock).create(
                selected_fixture,
                corpus.decision_id,
                corpus.dataset_id,
                "M12 authored comparison",
                corpus.model_identity,
                tuple(dump_record(binding) for binding in bindings),
                operation_id="m12-prepare-comparison",
                note="Independent authored ex-003 question; original exact requests retained.",
            )
            prepared_count = len(bindings)
        elif workflow == "G":
            planner = Planner(source, ProviderBackends(source, clock))
            plans = planner.prepare_orders(
                RunRequest(
                    decision_id=corpus.decision_id,
                    dataset_id=corpus.dataset_id,
                    mode="fixture",
                    fixture_set_id=original.id,
                    case_ids=("ex-001", "ex-003"),
                ),
                orders=2,
                seed=-(2**63),
            )
            if tuple(plan.selection.option_order for plan in plans) != (
                ORIGINAL_ORDER,
                MIN_SEED_ALTERNATE,
            ):
                raise RuntimeError("qualification_order_vector_mismatch")
            bindings = []
            for order_index, plan in enumerate(plans):
                for prepared in plan.prepared:
                    if prepared.request is None:
                        raise RuntimeError("qualification_expected_request_missing")
                    option_id = (
                        "question" if prepared.case_id == "ex-001" or order_index == 1 else "report"
                    )
                    bindings.append(
                        FixtureBinding(
                            id=f"m12-order-{order_index}-{prepared.case_id}",
                            case_id=prepared.case_id,
                            request=prepared.request,
                            answer=NormalizedAnswer(
                                question_id="category",
                                option_id=option_id,
                                reported_model=corpus.model_identity,
                            ),
                        )
                    )
            selected_fixture = "m12-choice-order-authored"
            FixtureService(source, clock).create(
                selected_fixture,
                corpus.decision_id,
                corpus.dataset_id,
                "M12 authored option orders",
                corpus.model_identity,
                tuple(dump_record(binding) for binding in bindings),
                operation_id="m12-prepare-orders",
                note="Installed compiler setup; independent order/answer oracles; zero dispatch.",
            )
            prepared_count = len(bindings)
        after = source.capture_snapshot()
        if tuple(item for item in before if item.key.collection != "fixtures") != tuple(
            item for item in after if item.key.collection != "fixtures"
        ):
            raise RuntimeError("qualification_preparation_changed_execution_or_other_source")
        original_keys = {item.key: item for item in before}
        after_keys = {item.key: item for item in after}
        if not original_keys.keys() <= after_keys.keys() or any(
            after_keys[key] != item for key, item in original_keys.items()
        ):
            raise RuntimeError("qualification_preparation_changed_original_record")
        allowed_new_keys = (
            {ResourceKey("fixtures", selected_fixture)} if workflow in {"C", "G"} else set()
        )
        if after_keys.keys() - original_keys.keys() != allowed_new_keys:
            raise RuntimeError("qualification_preparation_unexpected_new_record")
        write_metadata(
            output,
            {
                "workflow": workflow,
                "run_id": baseline.run_id,
                "evaluation_id": baseline.id,
                "evaluation_content_hash": baseline.content_hash,
                "result_snapshot_id": baseline.result_snapshot_id,
                "label_snapshot_id": baseline.label_snapshot_id,
                "decision_id": corpus.decision_id,
                "dataset_id": corpus.dataset_id,
                "fixture_set_id": selected_fixture,
                "original_fixture_set_id": original.id,
                "imported_selected_count": ResultInspection(source)
                .list(baseline.run_id, evaluation_id=baseline.id)
                .selected_count,
                "imported_fixture_calls": 11,
                "preparation_dispatch_calls": 0,
                "prepared_binding_count": prepared_count,
                "original_records_unchanged": True,
                "execution_records_unchanged": True,
                "original_order": ORIGINAL_ORDER,
                "min_seed_alternate": MIN_SEED_ALTERNATE,
                "max_seed_alternate": MAX_SEED_ALTERNATE,
            },
        )


def report_witness(project: Path, report_id: str, output: Path) -> None:
    with FileProjectSource(project) as source:
        service = ReportService(source, SetupClock())
        view = service.read(report_id)
        artifacts: dict[str, object] = {}
        for format in ("json", "markdown"):
            artifact = service.render(report_id, format=format)
            filename = f"{report_id}.{format}.bytes"
            write_private(output.parent / filename, artifact.body)
            artifacts[format] = {
                "file": filename,
                "bytes_hash": hashlib.sha256(artifact.body).hexdigest(),
                "byte_count": len(artifact.body),
            }
        write_metadata(
            output,
            {
                "report_id": report_id,
                "content_hash": view.record.content_hash,
                "artifacts": artifacts,
                "read_only_witness": True,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "report-witness"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--workflow", choices=("S", "C", "G", "R"))
    parser.add_argument("--report-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare" and args.workflow:
        prepare(args.project, args.workflow, args.output)
    elif args.action == "report-witness" and args.report_id:
        report_witness(args.project, args.report_id, args.output)
    else:
        raise RuntimeError("qualification_worker_arguments_invalid")


if __name__ == "__main__":
    main()
