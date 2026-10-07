"""Focused report behavior over one reusable saved fixture evidence graph."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import ValidationError

from deykit.application.comparisons import ComparisonService
from deykit.application.demo import DemoService
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.application.reports import ReportService
from deykit.cli.context import SystemClock
from deykit.contracts.artifacts import ArtifactWriteOutcome
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import (
    CommitReceipt,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.redaction import Sanitizer
from deykit.reports.models import RawChoices, RawMaterial, ReportRequest
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource
from deykit.storage.artifact_export import NativeArtifactWriter


@dataclass(frozen=True)
class FixtureGraph:
    root: Path
    run_id: str
    evaluation_id: str


@pytest.fixture(scope="session")
def fixture_graph(tmp_path_factory: pytest.TempPathFactory) -> FixtureGraph:
    root = tmp_path_factory.mktemp("saved-report-project") / "Deykit Fixture"
    clock = SystemClock()
    project = DemoService(
        lambda path, create: FileProjectSource(path, create=create), clock
    ).create(root, operation_id="report-demo")
    with FileProjectSource(root) as source:
        progress = asyncio.run(
            ExecutionService(source, source, ProviderBackends(source, clock), clock).start(
                RunRequest(
                    decision_id=project.decision_id,
                    dataset_id=project.dataset_id,
                    mode="fixture",
                    fixture_set_id=project.fixture_set_id,
                ),
                operation_id="report-fixture-run",
            )
        )
        evaluation = EvaluationService(source, clock).evaluate_saved(
            progress.run_id,
            progress.latest_result_snapshot_id,
            operation_id="report-fixture-evaluation",
        )
    return FixtureGraph(root, progress.run_id, evaluation.record.id)


@dataclass
class MemorySnapshotSource:
    """Narrow in-memory clone of immutable records for focused service cases."""

    records: dict[ResourceKey, StoredRecord]
    operations: dict[str, tuple[str, CommitReceipt]] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: tuple[StoredRecord, ...]) -> MemorySnapshotSource:
        return cls({item.key: item for item in records})

    @contextmanager
    def consistent_read(self):
        yield self

    def capture_snapshot(self, keys: tuple[ResourceKey, ...] | None = None):
        if keys is None:
            return tuple(self.records.values())
        return tuple(self.records[key] for key in keys if key in self.records)

    def operation_receipt(self, operation_id: str, *, intent_hash: str):
        previous = self.operations.get(operation_id)
        if previous is None:
            return None
        if previous[0] != intent_hash:
            raise ServiceFailure(ServiceError(code="conflict"))
        return previous[1]

    def commit(
        self,
        operation_id: str,
        changes: tuple[SourceChange, ...],
        *,
        intent_hash: str | None = None,
    ) -> CommitReceipt:
        previous = self.operation_receipt(operation_id, intent_hash=intent_hash or "")
        if previous is not None:
            return previous
        for change in changes:
            old = self.records.get(change.key)
            if (old.etag if old else None) != change.expected_etag:
                raise ServiceFailure(ServiceError(code="conflict"))
        saved = tuple(
            StoredRecord(change.key, change.body, bytes_hash(change.body))
            for change in changes
            if change.body is not None
        )
        for item in saved:
            self.records[item.key] = item
        receipt = CommitReceipt(operation_id, saved)
        self.operations[operation_id] = (intent_hash or "", receipt)
        return receipt


def snapshot(graph: FixtureGraph) -> tuple[StoredRecord, ...]:
    with FileProjectSource(graph.root) as source:
        return source.capture_snapshot()


def test_sanitizer_and_raw_material_keep_exact_source_and_opaque_bytes() -> None:
    sanitizer = Sanitizer(("secret-value",))
    assert sanitizer.text("Bearer secret-value") == "Bearer [REDACTED]"
    assert sanitizer.text(sanitizer.text("Bearer secret-value")) == "Bearer [REDACTED]"
    assert sanitizer.bytes(b"Bearer secret-value") == b"Bearer [REDACTED]"
    assert sanitizer.bytes(sanitizer.bytes(b"Bearer secret-value")) == b"Bearer [REDACTED]"

    exact = '{"n":9007199254740993,"d":0.123456789012345678901234567890}'
    source_hash = "0" * 64
    preserved = RawMaterial(
        category="input",
        run_id="run-1",
        case_id="case-1",
        encoding="json_source_utf8",
        source=exact,
        identity_kind="input_semantic_hash",
        original_hash=source_hash,
        sanitized_hash=bytes_hash(exact.encode()),
    )
    assert preserved.source == exact
    assert preserved.changed_by_redaction is False

    opaque = b"\xff\x00A\x80"
    encoded = "/wBBgA=="
    canonical = RawMaterial(
        category="response",
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        encoding="base64",
        source=encoded,
        identity_kind="stored_response_bytes_hash",
        original_hash=bytes_hash(opaque),
        sanitized_hash=bytes_hash(opaque),
    )
    assert canonical.source == encoded
    with pytest.raises(ValidationError):
        RawMaterial(
            category="response",
            run_id="run-1",
            case_id="case-1",
            encoding="base64",
            source="/wBBgA=",
            identity_kind="stored_response_bytes_hash",
            original_hash=source_hash,
            sanitized_hash=source_hash,
        )


def test_saved_run_report_copies_independent_fixture_facts_and_renders(
    fixture_graph: FixtureGraph,
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    service = ReportService(source, SystemClock(), lambda: "report-run")
    report = service.create(
        ReportRequest(
            target_id=fixture_graph.run_id,
            target_kind="run",
            evaluation_id=fixture_graph.evaluation_id,
        ),
        operation_id="report-run-create",
    )

    evaluation = report.content.evaluations[0]
    metrics = evaluation.metrics
    assert metrics.summary.selected_count == 12
    assert metrics.summary.status_counts.valid == 10
    assert metrics.summary.status_counts.input_invalid == 1
    assert metrics.summary.status_counts.response_error == 1
    assert metrics.summary.status_counts.pending == 0
    assert metrics.summary.status_counts.unknown == 0
    assert (metrics.summary.coverage.numerator, metrics.summary.coverage.denominator) == (10, 12)
    assert (metrics.summary.set_accuracy.numerator, metrics.summary.set_accuracy.denominator) == (
        6,
        8,
    )
    assert (metrics.summary.macro_f1.numerator, metrics.summary.macro_f1.denominator) == (
        47,
        60,
    )
    assert metrics.baseline.fit_support == 9
    assert (metrics.baseline.accuracy.numerator, metrics.baseline.accuracy.denominator) == (3, 8)
    assert report.content.raw_material == ()
    assert report.record.includes_raw_input is False
    assert report.record.includes_raw_request is False
    assert report.record.includes_raw_response is False

    first = service.render(report.record.id, format="json")
    second = service.render(report.record.id, format="json")
    assert first.body == second.body
    assert first.body.endswith(b"\n")
    assert first.bytes_hash == bytes_hash(first.body)
    assert (
        b"authored_fixture_not_provider_quality"
        in service.render(report.record.id, format="markdown").body
    )
    assert service.metadata(report.record.id).target_kind == "run"
    assert service.list(limit=1).items[0].report_id == report.record.id


def test_replay_precedes_target_lookup_and_id_or_clock(fixture_graph: FixtureGraph) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    request = ReportRequest(target_id=fixture_graph.run_id, target_kind="run")
    first = ReportService(source, SystemClock(), lambda: "report-replay").create(
        request, operation_id="report-replay-create"
    )
    source.records[ResourceKey("comparisons", fixture_graph.run_id)] = StoredRecord(
        ResourceKey("comparisons", fixture_graph.run_id), b"reserved collision", "collision"
    )

    class ThrowingClock:
        def utc_now(self) -> str:
            raise AssertionError("receipt replay must not read the clock")

        def monotonic(self) -> float:
            raise AssertionError("receipt replay must not read the clock")

    def forbidden_id() -> str:
        raise AssertionError("receipt replay must not generate an ID")

    replay = ReportService(source, ThrowingClock(), forbidden_id).create(
        request, operation_id="report-replay-create"
    )
    assert replay.replayed is True
    assert replay.record.id == first.record.id
    assert replay.record.content_hash == first.record.content_hash
    with pytest.raises(ServiceFailure):
        ReportService(source, ThrowingClock(), forbidden_id).create(
            ReportRequest(
                target_id=fixture_graph.run_id,
                target_kind="run",
                raw=RawChoices(inputs=True),
            ),
            operation_id="report-replay-create",
        )


def test_comparison_report_retains_both_admitted_contexts(fixture_graph: FixtureGraph) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    clock = SystemClock()
    comparison = ComparisonService(source, clock, lambda: "comparison-self").create(
        fixture_graph.evaluation_id,
        fixture_graph.evaluation_id,
        operation_id="comparison-self-create",
    )
    report = ReportService(source, clock, lambda: "report-comparison").create(
        ReportRequest(target_id=comparison.record.id, target_kind="comparison"),
        operation_id="report-comparison-create",
    )
    assert report.content.comparison == comparison.outcomes
    assert tuple(item.context.evaluation_id for item in report.content.evaluations) == (
        fixture_graph.evaluation_id,
        fixture_graph.evaluation_id,
    )
    assert report.content.target.comparison_id == comparison.record.id
    assert ReportService(source, clock).read(report.record.id).content == report.content


def test_file_project_report_export_writes_rendered_bytes_after_source_read(
    fixture_graph: FixtureGraph, tmp_path: Path
) -> None:
    clock = SystemClock()
    with FileProjectSource(fixture_graph.root) as source:
        report = ReportService(source, clock, lambda: "report-file").create(
            ReportRequest(
                target_id=fixture_graph.run_id,
                target_kind="run",
                evaluation_id=fixture_graph.evaluation_id,
            ),
            operation_id="report-file-create",
        )
        destination = tmp_path / "report.json"

        class SourceProbingWriter:
            def write(self, path, body, *, display_is_safe=None) -> ArtifactWriteOutcome:
                assert source.capture_snapshot()
                return NativeArtifactWriter().write(path, body, display_is_safe=display_is_safe)

        outcome = ReportService(source, clock).export(
            report.record.id,
            format="json",
            destination=str(destination),
            writer=SourceProbingWriter(),
        )
        expected = ReportService(source, clock).render(report.record.id, format="json")
        assert outcome.success is True
        assert destination.read_bytes() == expected.body
        assert outcome.artifact_hash == expected.bytes_hash
        assert source.read(ResourceKey("reports", report.record.id)) is not None
