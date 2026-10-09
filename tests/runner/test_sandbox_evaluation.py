"""Packaged authored Sandbox runs through exact fixture bindings and real storage."""

from __future__ import annotations

import asyncio
from pathlib import Path

from deykit.application.demo import DemoService
from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.cli.context import SystemClock
from deykit.contracts.codec import load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import FixtureSet, ProviderProfile, ResultSnapshot
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.fixtures import FixtureTransportFactory
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource


class SandboxBackends:
    compiler = JevChoiceCompiler()

    def __init__(self, source: FileProjectSource, fixture_id: str) -> None:
        fixture_source = source.read(ResourceKey("fixtures", fixture_id))
        assert fixture_source is not None
        self.fixture_set = load_record(FixtureSet, fixture_source.body)
        self.profile_id = None
        self.source = source

    def profile(self, provider_id: str | None, fixture_set_id: str | None) -> ProviderProfile:
        assert fixture_set_id == self.fixture_set.id
        ids = self.source.list_ids("providers")
        assert len(ids) == 1
        profile_source = self.source.read(ResourceKey("providers", ids[0]))
        assert profile_source is not None
        return load_record(ProviderProfile, profile_source.body)

    def resolve(self, profile: ProviderProfile, fixture_set_id: str | None) -> SandboxBackends:
        assert fixture_set_id == self.fixture_set.id
        self.transport = FixtureTransportFactory(self.fixture_set, profile)
        return self

    def preflight(self, decision_id: str, dataset_id: str, definition=None):
        assert (decision_id, dataset_id) == (
            self.fixture_set.decision_id,
            self.fixture_set.dataset_id,
        )
        return None

    def for_case(self, case_id: str):
        return self.transport.for_case(case_id)


def test_packaged_authored_sandbox_exact_evaluation(tmp_path: Path):
    clock = SystemClock()
    path = tmp_path / "sandbox"
    info = DemoService(
        lambda root, create: FileProjectSource(root, create=create),
        clock,
        staging_factory=DemoStagingSource,
    ).create(
        path, operation_id="demo"
    )
    with FileProjectSource(path) as source:
        backend = SandboxBackends(source, info.fixture_set_id)
        runner = ExecutionService(source, source, backend, clock)
        progress = asyncio.run(
            runner.start(
                RunRequest(
                    decision_id=info.decision_id,
                    dataset_id=info.dataset_id,
                    mode="fixture",
                    fixture_set_id=info.fixture_set_id,
                ),
                operation_id="sandbox-run",
            )
        )
        assert progress.attempts_used == 11
        snapshots = (
            load_record(ResultSnapshot, source.read(ResourceKey("result_snapshots", item)).body)
            for item in source.list_ids("result_snapshots")
        )
        latest = max(snapshots, key=lambda item: item.through_event_sequence)
        evaluation = EvaluationService(source, clock).evaluate_saved(
            progress.run_id, latest.id, operation_id="sandbox-evaluation"
        )
        summary = evaluation.metrics["summary"]
        assert summary["selected_count"] == 12
        assert summary["status_counts"] == {
            "pending": 0,
            "input_invalid": 1,
            "response_error": 1,
            "unknown": 0,
            "valid": 10,
        }
        assert summary["coverage"]["numerator"] == 10
        assert summary["coverage"]["denominator"] == 12
        assert summary["set_accuracy"]["numerator"] == 6
        assert summary["set_accuracy"]["denominator"] == 8
        assert summary["confusion_matrix"] == [
            [2, 1, 0, 0],
            [0, 2, 0, 0],
            [1, 0, 1, 0],
            [0, 0, 0, 1],
        ]
        assert summary["macro_f1"]["numerator"] == 47
        assert summary["macro_f1"]["denominator"] == 60
        assert evaluation.metrics["baseline"]["fit_support"] == 9
        assert evaluation.metrics["baseline"]["accuracy"]["numerator"] == 3
        assert evaluation.metrics["baseline"]["accuracy"]["denominator"] == 8
        assert evaluation.metrics["evidence_mode"] == "fixture"
        assert evaluation.metrics["usage"]["total_input_tokens"] is None
