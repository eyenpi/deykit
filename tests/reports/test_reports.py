"""Focused report behavior over one reusable saved fixture evidence graph."""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from pydantic import ValidationError

import deykit.application.reports as reports_module
from deykit.application.comparisons import ComparisonService
from deykit.application.demo import DemoService
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService, evaluation_hash
from deykit.application.execution import ExecutionService
from deykit.application.fixtures import FixtureService
from deykit.application.labels import LabelService
from deykit.application.reports import ReportService
from deykit.cli.context import SystemClock
from deykit.contracts.artifacts import ArtifactWriteOutcome
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.ports import (
    CommitReceipt,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import (
    CaseRecord,
    ComparisonRecord,
    EvaluationRecord,
    NormalizedAnswer,
    PreparedCase,
    ReportRecord,
)
from deykit.contracts.redaction import Sanitizer
from deykit.reports.admission import report_hash
from deykit.reports.models import RawChoices, RawMaterial, ReportContent, ReportRequest
from deykit.reports.projection import project_json_source, project_opaque_response_bytes
from deykit.reports.render import render_content
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource
from deykit.storage.artifact_export import NativeArtifactWriter


@dataclass(frozen=True)
class FixtureGraph:
    root: Path
    run_id: str
    evaluation_id: str
    reevaluation_id: str
    comparison_id: str
    records: tuple[StoredRecord, ...]


@pytest.fixture(scope="session")
def fixture_graph(tmp_path_factory: pytest.TempPathFactory) -> FixtureGraph:
    reused_root = os.environ.get("DEYKIT_TEST_REPORT_PROJECT")
    if reused_root is not None:
        root = Path(reused_root).resolve()
        with FileProjectSource(root) as source:
            records = source.capture_snapshot()
        comparisons = tuple(
            load_record(ComparisonRecord, item.body)
            for item in records
            if item.key.collection == "comparisons"
        )
        assert len(comparisons) == 1
        comparison = comparisons[0]
        evaluations = {
            item.key.resource_id: load_record(EvaluationRecord, item.body)
            for item in records
            if item.key.collection == "evaluations"
        }
        left = evaluations[comparison.left_evaluation_id]
        right = evaluations[comparison.right_evaluation_id]
        assert left.id == comparison.left_evaluation_id
        assert right.id == comparison.right_evaluation_id
        reevaluations = tuple(
            item
            for item in evaluations.values()
            if item.run_id == left.run_id and item.mode == "saved_answer_reevaluation"
        )
        assert len(reevaluations) == 1
        return FixtureGraph(
            root,
            left.run_id,
            left.id,
            reevaluations[0].id,
            comparison.id,
            records,
        )

    root = tmp_path_factory.mktemp("saved-report-project") / "Deykit Fixture"
    clock = SystemClock()
    project = DemoService(
        lambda path, create: FileProjectSource(path, create=create), clock
    ).create(root, operation_id="report-demo")
    with FileProjectSource(root) as source:
        fixture_service = FixtureService(source, clock)
        original = fixture_service.read(project.fixture_set_id).fixture_set
        corrected_bindings = tuple(
            binding.model_copy(
                update={
                    "answer": NormalizedAnswer(
                        question_id="category",
                        option_id="question",
                        reported_model=original.model_identity,
                    )
                }
            )
            if binding.case_id == "ex-003"
            else binding
            for binding in original.bindings
        )
        fixture_service.create(
            "corrected",
            project.decision_id,
            project.dataset_id,
            "Authored correction",
            original.model_identity,
            tuple(dump_record(binding) for binding in corrected_bindings),
            operation_id="report-corrected-fixture",
        )
        runner = ExecutionService(source, source, ProviderBackends(source, clock), clock)
        evaluations = EvaluationService(source, clock)

        def execute(fixture_id: str, run_operation: str):
            progress = asyncio.run(
                runner.start(
                    RunRequest(
                        decision_id=project.decision_id,
                        dataset_id=project.dataset_id,
                        mode="fixture",
                        fixture_set_id=fixture_id,
                    ),
                    operation_id=run_operation,
                )
            )
            assert progress.latest_result_snapshot_id is not None
            return evaluations.evaluate_saved(
                progress.run_id,
                progress.latest_result_snapshot_id,
                operation_id=f"evaluate-{run_operation}",
            )

        left = execute(project.fixture_set_id, "report-left-run")
        right = execute("corrected", "report-right-run")
        comparison = ComparisonService(source, clock, lambda: "report-a36-comparison").create(
            left.record.id,
            right.record.id,
            operation_id="report-a36-comparison",
        )
        labels = LabelService(source, clock)
        labels.set(
            labels.read(project.decision_id, project.dataset_id, "ex-001").review,
            ("question", "report"),
            provenance="human",
            operation_id="report-current-label-edit",
        )
        reevaluation = evaluations.reevaluate_current_labels(
            left.record.run_id,
            left.record.result_snapshot_id,
            operation_id="report-current-label-evaluation",
        )
        records = source.capture_snapshot()
    return FixtureGraph(
        root,
        left.record.run_id,
        left.record.id,
        reevaluation.record.id,
        comparison.record.id,
        records,
    )


@dataclass
class MemorySnapshotSource:
    """Narrow in-memory clone of immutable records for focused service cases."""

    records: dict[ResourceKey, StoredRecord]
    operations: dict[str, tuple[str, CommitReceipt]] = field(default_factory=dict)
    commit_calls: int = 0

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
        self.commit_calls += 1
        previous = self.operation_receipt(operation_id, intent_hash=intent_hash or "")
        if previous is not None:
            return previous
        for change in changes:
            old = self.records.get(change.key)
            if (old.etag if old else None) != change.expected_etag:
                raise ServiceFailure(ServiceError(code="conflict"))
        deleted = tuple(change.key for change in changes if change.body is None)
        saved = tuple(
            StoredRecord(change.key, change.body, bytes_hash(change.body))
            for change in changes
            if change.body is not None
        )
        for key in deleted:
            self.records.pop(key, None)
        for item in saved:
            self.records[item.key] = item
        receipt = CommitReceipt(operation_id, saved, deleted_keys=deleted)
        self.operations[operation_id] = (intent_hash or "", receipt)
        return receipt


def snapshot(graph: FixtureGraph) -> tuple[StoredRecord, ...]:
    return graph.records


def test_sanitizer_and_raw_material_keep_exact_source_and_opaque_bytes() -> None:
    sanitizer = Sanitizer(("secret-value",))
    assert sanitizer.text("Bearer secret-value") == "Bearer [REDACTED]"
    assert sanitizer.text(sanitizer.text("Bearer secret-value")) == "Bearer [REDACTED]"
    assert sanitizer.bytes(b"Bearer secret-value") == b"Bearer [REDACTED]"
    assert sanitizer.bytes(sanitizer.bytes(b"Bearer secret-value")) == b"Bearer [REDACTED]"
    assert sanitizer.bytes(b"secret-value\xff") == b"[REDACTED]\xff"
    assert sanitizer.text("Bearer [REDACTED] TOKEN") == "Bearer [REDACTED] TOKEN"
    assert sanitizer.text("Bearer [REDACTED]TOKEN") == "Bearer [REDACTED]"
    assert sanitizer.bytes(b"Bearer [REDACTED]TOKEN\xff") == b"Bearer [REDACTED]"

    projected_opaque = project_opaque_response_bytes(
        b"\xff\x00A\x80",
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        sanitizer=Sanitizer(),
    )
    assert projected_opaque.source == "/wBBgA=="
    assert projected_opaque.encoding == "base64"
    assert projected_opaque.original_hash == bytes_hash(b"\xff\x00A\x80")
    assert projected_opaque.sanitized_hash == bytes_hash(b"\xff\x00A\x80")
    exact_utf8 = project_opaque_response_bytes(
        "opaque-compatible λ".encode(),
        run_id="run-1",
        case_id="case-1",
        attempt_id=None,
        sanitizer=Sanitizer(),
    )
    assert exact_utf8.encoding == "utf8"
    assert exact_utf8.source == "opaque-compatible λ"
    assert exact_utf8.changed_by_redaction is False
    redacted_opaque = project_opaque_response_bytes(
        b"Bearer known-secret\xff",
        run_id="run-1",
        case_id="case-1",
        attempt_id=None,
        sanitizer=Sanitizer(("known-secret",)),
    )
    assert redacted_opaque.encoding == "utf8"
    assert redacted_opaque.source == "Bearer [REDACTED]"
    assert redacted_opaque.original_hash == bytes_hash(b"Bearer known-secret\xff")
    assert redacted_opaque.sanitized_hash == bytes_hash(b"Bearer [REDACTED]")
    assert redacted_opaque.changed_by_redaction is True

    exact = '{"n":9007199254740993,"d":0.123456789012345678901234567890}'
    projected_source, changed = project_json_source(exact, Sanitizer())
    assert projected_source == exact
    assert changed is False
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
    original_evaluation = load_record(
        EvaluationRecord,
        source.records[ResourceKey("evaluations", fixture_graph.evaluation_id)].body,
    )
    assert "schema_version" not in parse_json(original_evaluation.metrics_source)
    saved_content = parse_json(report.record.content_source)
    assert isinstance(saved_content, dict)
    saved_evaluations = saved_content["evaluations"]
    assert isinstance(saved_evaluations, list)
    saved_metrics = saved_evaluations[0]["metrics"]
    assert isinstance(saved_metrics, dict)
    assert saved_metrics["schema_version"] == 1
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
    markdown = service.render(report.record.id, format="markdown").body.decode("utf-8")
    for fragment in (
        "- Fitting support: 9; excluded acceptable sets:",
        "- Evaluation snapshots: `",
        "- Evaluation splits:",
        "- Selected: 12; scoring population: provider_valid_applicable_labels; scored:",
        "- Dispatched attempts:",
        "- Usage source:",
        "reported at:",
    ):
        assert fragment in markdown
    assert service.metadata(report.record.id).target_kind == "run"
    assert service.list(limit=1).items[0].report_id == report.record.id


def test_evaluation_and_historical_run_selectors_keep_pinned_labels(
    fixture_graph: FixtureGraph,
) -> None:
    records = snapshot(fixture_graph)
    source = MemorySnapshotSource.from_records(records)
    clock = SystemClock()

    evaluation_report = ReportService(source, clock, lambda: "report-evaluation").create(
        ReportRequest(target_id=fixture_graph.evaluation_id, target_kind="evaluation"),
        operation_id="report-evaluation-create",
    )
    historical_run = ReportService(source, clock, lambda: "report-historical").create(
        ReportRequest(
            target_id=fixture_graph.run_id,
            target_kind="run",
            evaluation_id=fixture_graph.evaluation_id,
        ),
        operation_id="report-historical-create",
    )
    reevaluated_run = ReportService(source, clock, lambda: "report-reevaluated").create(
        ReportRequest(
            target_id=fixture_graph.run_id,
            target_kind="run",
            evaluation_id=fixture_graph.reevaluation_id,
        ),
        operation_id="report-reevaluated-create",
    )

    assert evaluation_report.content.evaluations[0].context.label_snapshot_id == (
        historical_run.content.evaluations[0].context.label_snapshot_id
    )
    assert historical_run.content.evaluations[0].context.evaluation_id == (
        fixture_graph.evaluation_id
    )
    assert reevaluated_run.content.evaluations[0].context.evaluation_id == (
        fixture_graph.reevaluation_id
    )
    assert reevaluated_run.content.evaluations[0].context.label_snapshot_id != (
        historical_run.content.evaluations[0].context.label_snapshot_id
    )


def test_all_raw_switches_use_real_projection_and_preserve_original_sources(
    fixture_graph: FixtureGraph,
) -> None:
    records = snapshot(fixture_graph)
    cases = {
        item.key.resource_id: load_record(CaseRecord, item.body)
        for item in records
        if item.key.collection == "cases"
    }
    prepared = {
        item.key.resource_id: load_record(PreparedCase, item.body)
        for item in records
        if item.key.collection == "prepared_cases" and item.key.scope == (fixture_graph.run_id,)
    }
    for mask in range(8):
        choices = RawChoices(
            inputs=bool(mask & 1),
            requests=bool(mask & 2),
            responses=bool(mask & 4),
        )
        source = MemorySnapshotSource.from_records(records)
        report = ReportService(
            source, SystemClock(), lambda mask=mask: f"report-raw-{mask}"
        ).create(
            ReportRequest(
                target_id=fixture_graph.run_id,
                target_kind="run",
                evaluation_id=fixture_graph.evaluation_id,
                raw=choices,
            ),
            operation_id=f"report-raw-{mask}",
        )
        expected = {
            category
            for category, enabled in (
                ("input", choices.inputs),
                ("request", choices.requests),
                ("response", choices.responses),
            )
            if enabled
        }
        assert {item.category for item in report.content.raw_material} == expected
        for material in report.content.raw_material:
            if material.category == "input":
                assert material.source == cases[material.case_id].input_source
                assert material.changed_by_redaction is False
            elif material.category == "request":
                request = prepared[material.case_id].request
                if request is None:
                    assert material.source is None
                    assert material.unavailable_reason == "request_not_prepared"
                else:
                    assert material.source == request.body.decode("utf-8", "strict")
                    assert material.original_hash == request.body_hash
                    assert material.sanitized_hash == bytes_hash(request.body)
                    assert material.changed_by_redaction is False
                    assert material.identity_kind == "prepared_request_bytes_hash"
                    assert material.attempt_id is None
            elif material.category == "response":
                assert material.encoding in (None, "json_source_utf8")
        assert report.record.includes_raw_input is choices.inputs
        assert report.record.includes_raw_request is choices.requests
        assert report.record.includes_raw_response is choices.responses


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
    with pytest.raises(ServiceFailure) as intent_failure:
        ReportService(source, ThrowingClock(), forbidden_id).create(
            ReportRequest(
                target_id=fixture_graph.run_id,
                target_kind="run",
                raw=RawChoices(inputs=True),
            ),
            operation_id="report-replay-create",
        )
    assert intent_failure.value.error.code == "conflict"


def test_comparison_report_retains_both_admitted_contexts(fixture_graph: FixtureGraph) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    clock = SystemClock()
    report = ReportService(source, clock, lambda: "report-comparison").create(
        ReportRequest(
            target_id=fixture_graph.comparison_id,
            target_kind="comparison",
            raw=RawChoices(inputs=True),
        ),
        operation_id="report-comparison-create",
    )
    assert report.content.comparison is not None
    outcomes = report.content.comparison
    assert outcomes.quality_denominator == 8
    assert {key: value for key, value in outcomes.primary_counts.items() if value} == {
        "both_correct": 6,
        "improved": 1,
        "both_wrong": 1,
        "unlabelled_agreement": 2,
        "unavailable_answer": 2,
    }
    assert outcomes.primary_counts["regressed"] == 0
    assert outcomes.left_correct_count == 6
    assert outcomes.right_correct_count == 7
    assert len(outcomes.cases) == 12
    assert sum(outcomes.primary_counts.values()) == 12
    assert sum(item.bucket == "improved" for item in outcomes.cases) == 1
    assert sum(item.bucket == "regressed" for item in outcomes.cases) == 0
    assert sum(item.bucket == "both_wrong" for item in outcomes.cases) == 1
    assert tuple(item.context.evaluation_id for item in report.content.evaluations) == (
        fixture_graph.evaluation_id,
        load_record(
            ComparisonRecord,
            source.records[ResourceKey("comparisons", fixture_graph.comparison_id)].body,
        ).right_evaluation_id,
    )
    assert report.content.target.comparison_id == fixture_graph.comparison_id
    assert ReportService(source, clock).read(report.record.id).content == report.content
    comparison_markdown = (
        ReportService(source, clock)
        .render(report.record.id, format="markdown")
        .body.decode("utf-8")
    )
    assert comparison_markdown.index("## Evaluation contexts") < comparison_markdown.index(
        "- Results:"
    )
    assert (
        comparison_markdown.index("### Class metrics")
        < comparison_markdown.index("### Confusion matrix")
        < comparison_markdown.index("### Baseline")
        < comparison_markdown.index("### Latency and usage")
        < comparison_markdown.rindex("### Case outcomes")
        < comparison_markdown.index("## Comparison")
        < comparison_markdown.index("## Explicitly included raw material")
    )


def test_report_admission_rejects_rehashed_context_and_missing_persisted_version(
    fixture_graph: FixtureGraph,
) -> None:
    for mutation in ("context", "content-version", "metrics-version"):
        source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
        service = ReportService(
            source, SystemClock(), lambda mutation=mutation: f"report-admission-{mutation}"
        )
        view = service.create(
            ReportRequest(target_id=fixture_graph.run_id, target_kind="run"),
            operation_id=f"report-admission-{mutation}-create",
        )
        stored = source.records[ResourceKey("reports", view.record.id)]
        if mutation == "context":
            tree = parse_json(view.record.content_source)
            assert isinstance(tree, dict)
            evaluations = tree["evaluations"]
            assert isinstance(evaluations, list)
            context = evaluations[0]["context"]
            assert isinstance(context, dict)
            context["requested_model"] = "forged-model"
            content_source = dump_json(tree)
            changed = view.record.model_copy(update={"content_source": content_source})
            changed = changed.model_copy(
                update={"content_hash": report_hash(changed, view.content)}
            )
            expected_reason = "report_link_mismatch"
        else:
            tree = parse_json(view.record.content_source)
            assert isinstance(tree, dict)
            if mutation == "content-version":
                del tree["schema_version"]
            else:
                evaluations = tree["evaluations"]
                assert isinstance(evaluations, list)
                metrics = evaluations[0]["metrics"]
                assert isinstance(metrics, dict)
                del metrics["schema_version"]
            content_source = dump_json(tree)
            changed = view.record.model_copy(update={"content_source": content_source})
            changed = changed.model_copy(
                update={"content_hash": report_hash(changed, view.content)}
            )
            expected_reason = "missing_schema_version"
        body = dump_record(changed)
        source.records[stored.key] = StoredRecord(stored.key, body, bytes_hash(body))
        with pytest.raises(ServiceFailure) as failure:
            service.read(view.record.id)
        assert failure.value.error.code == "incompatible_data"
        assert failure.value.error.reason == expected_reason


def test_miskeyed_evaluation_body_cannot_be_reported(fixture_graph: FixtureGraph) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    key = ResourceKey("evaluations", fixture_graph.evaluation_id)
    original = source.records[key]
    evaluation = load_record(EvaluationRecord, original.body)
    forged = evaluation.model_copy(update={"id": "different-evaluation"})
    forged = forged.model_copy(update={"content_hash": evaluation_hash(forged)})
    body = dump_record(forged)
    source.records[key] = StoredRecord(key, body, bytes_hash(body))

    with pytest.raises(ServiceFailure):
        ReportService(source, SystemClock(), lambda: "report-miskeyed").create(
            ReportRequest(
                target_id=fixture_graph.run_id,
                target_kind="run",
                evaluation_id=fixture_graph.evaluation_id,
            ),
            operation_id="report-miskeyed-create",
        )
    assert source.commit_calls == 0
    assert ResourceKey("reports", "report-miskeyed") not in source.records


def test_sensitive_exact_body_etag_fails_before_report_commit(fixture_graph: FixtureGraph) -> None:
    class FixedClock:
        def utc_now(self) -> str:
            return "2026-10-05T12:00:00Z"

        def monotonic(self) -> float:
            return 0.0

    records = snapshot(fixture_graph)
    request = ReportRequest(target_id=fixture_graph.run_id, target_kind="run")
    baseline = ReportService(
        MemorySnapshotSource.from_records(records), FixedClock(), lambda: "report-etag"
    ).create(request, operation_id="report-etag-baseline")
    body_etag = bytes_hash(dump_record(baseline.record))
    source = MemorySnapshotSource.from_records(records)
    service = ReportService(
        source, FixedClock(), lambda: "report-etag", sanitizer=Sanitizer((body_etag,))
    )

    with pytest.raises(ServiceFailure) as failure:
        service.create(request, operation_id="report-etag-sensitive")
    assert failure.value.error.reason == "report_sensitive_identity"
    assert source.commit_calls == 0
    assert ResourceKey("reports", "report-etag") not in source.records


@pytest.mark.parametrize(
    "mutation", ("empty", "extra", "deleted", "key", "body", "etag", "operation")
)
def test_fresh_commit_receipt_must_match_exact_report_write(
    fixture_graph: FixtureGraph, mutation: str
) -> None:
    class MutatingReceiptSource(MemorySnapshotSource):
        def commit(self, operation_id, changes, *, intent_hash=None):
            receipt = super().commit(operation_id, changes, intent_hash=intent_hash)
            if mutation == "empty":
                return replace(receipt, changes=())
            if mutation == "extra":
                return replace(receipt, changes=receipt.changes * 2)
            if mutation == "deleted":
                return replace(receipt, deleted_keys=(ResourceKey("reports", "deleted-report"),))
            saved = receipt.changes[0]
            if mutation == "key":
                changed = replace(saved, key=ResourceKey("reports", "other-report"))
                return replace(receipt, changes=(changed,))
            if mutation == "body":
                changed = replace(saved, body=b"forged report body")
                return replace(receipt, changes=(changed,))
            if mutation == "etag":
                changed = replace(saved, etag="0" * 64)
                return replace(receipt, changes=(changed,))
            return replace(receipt, operation_id="other-operation")

    source = MutatingReceiptSource.from_records(snapshot(fixture_graph))
    with pytest.raises(ServiceFailure) as failure:
        ReportService(source, SystemClock(), lambda: "report-receipt").create(
            ReportRequest(target_id=fixture_graph.run_id, target_kind="run"),
            operation_id="report-receipt-create",
        )
    assert failure.value.error.code == "incompatible_data"
    assert failure.value.error.reason == "invalid_report_receipt"


def test_strict_sanitizer_rejects_replay_and_read_that_change_frozen_evidence(
    fixture_graph: FixtureGraph,
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    request = ReportRequest(target_id=fixture_graph.run_id, target_kind="run")
    ReportService(source, SystemClock(), lambda: "report-sanitizer").create(
        request, operation_id="report-sanitizer-create"
    )
    record = source.records[ResourceKey("reports", "report-sanitizer")]
    saved = load_record(ReportRecord, record.body)
    content = ReportContent.model_validate_json(saved.content_source, context={"persisted": True})
    secret = content.evaluations[0].context.requested_model
    assert secret
    strict = ReportService(source, SystemClock(), sanitizer=Sanitizer((secret,)))
    with pytest.raises(ServiceFailure) as read_failure:
        strict.read(saved.id)
    assert read_failure.value.error.reason == "report_redaction_context_mismatch"
    with pytest.raises(ServiceFailure) as replay_failure:
        strict.create(request, operation_id="report-sanitizer-create")
    assert replay_failure.value.error.reason == "report_redaction_context_mismatch"


def test_renderer_fences_raw_material_and_enforces_artifact_bound(
    fixture_graph: FixtureGraph,
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    report = ReportService(source, SystemClock(), lambda: "report-render-bound").create(
        ReportRequest(
            target_id=fixture_graph.run_id,
            target_kind="run",
            raw=RawChoices(inputs=True),
        ),
        operation_id="report-render-bound-create",
    )
    assert report.content.raw_material
    raw = report.content.raw_material[0].model_copy(
        update={"source": "trusted payload ```\r\n# injected heading\rnext"}
    )
    changed = report.content.model_copy(update={"raw_material": (raw,)})
    markdown = render_content(report.record, changed, "markdown").body.decode()
    expected_raw = (
        f"### input: run `{raw.run_id}`, case `{raw.case_id}`, attempt `none`\n"
        f"Encoding: `json_source_utf8`; original hash: `{raw.original_hash}`; "
        f"sanitized hash: `{raw.sanitized_hash}`\n"
        "````\ntrusted payload ```\n# injected heading\nnext\n````"
    )
    assert markdown.endswith(expected_raw)
    assert report.content.raw_material[0].source != raw.source
    assert (
        render_content(report.record, changed, "json").body
        == render_content(report.record, report.content, "json").body
    )

    golden_record = ReportRecord(
        id="report-golden",
        evaluation_ids=(),
        result_snapshot_ids=(),
        label_snapshot_ids=(),
        content_source="{}",
        content_hash="0" * 64,
        created_at="2026-10-05T12:00:00Z",
    )
    golden_json = render_content(golden_record, report.content, "json").body
    assert golden_json == (
        b'{"content":{},"content_hash":"0000000000000000000000000000000000000000000000000000000000000000",'
        b'"created_at":"2026-10-05T12:00:00Z","report_id":"report-golden","schema_version":1}\n'
    )

    oversized = raw.model_copy(update={"source": "x" * (8 * 1024 * 1024)})
    oversized_content = report.content.model_copy(update={"raw_material": (oversized,)})
    with pytest.raises(ValueError, match="report_artifact_limit"):
        render_content(report.record, oversized_content, "markdown")


def test_service_render_maps_fixed_renderer_failures_to_safe_errors(
    fixture_graph: FixtureGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    service = ReportService(source, SystemClock(), lambda: "report-render-safe")
    report = service.create(
        ReportRequest(target_id=fixture_graph.run_id, target_kind="run"),
        operation_id="report-render-safe-create",
    )
    for pure_reason in ("report_artifact_limit", "invalid_report_format"):

        def reject(*args, reason=pure_reason, **kwargs):
            raise ValueError(reason)

        monkeypatch.setattr(reports_module, "render_content", reject)
        with pytest.raises(ServiceFailure) as failure:
            service.render(report.record.id, format="markdown")
        assert failure.value.error.code == "validation_error"
        assert failure.value.error.reason == pure_reason
        assert failure.value.error.message == "The supplied data is invalid."


def test_report_content_limit_fails_before_memory_source_write(
    fixture_graph: FixtureGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    original_project = reports_module.project_evaluation

    def oversized_projection(*args, **kwargs):
        projected, materials = original_project(*args, **kwargs)
        case_id = projected.cases[0].case_id
        large_source = "x" * 1_048_576
        material = RawMaterial(
            category="input",
            run_id=fixture_graph.run_id,
            case_id=case_id,
            encoding="utf8",
            source=large_source,
            identity_kind="input_semantic_hash",
            original_hash="0" * 64,
            sanitized_hash=bytes_hash(large_source.encode()),
        )
        return projected, (*materials, material)

    monkeypatch.setattr(reports_module, "project_evaluation", oversized_projection)
    with pytest.raises(ServiceFailure) as failure:
        ReportService(source, SystemClock(), lambda: "report-over-limit").create(
            ReportRequest(
                target_id=fixture_graph.run_id,
                target_kind="run",
                raw=RawChoices(inputs=True),
            ),
            operation_id="report-over-limit-create",
        )
    assert failure.value.error.reason == "report_content_limit"
    assert source.commit_calls == 0
    assert ResourceKey("reports", "report-over-limit") not in source.records


def test_reserved_group_and_nonapplicable_selectors_and_target_collision_fail(
    fixture_graph: FixtureGraph,
) -> None:
    with pytest.raises(ValidationError):
        ReportRequest(
            target_id=fixture_graph.run_id,
            target_kind="run",
            group_snapshot_id="reserved-group",
        )

    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    service = ReportService(source, SystemClock(), lambda: "report-invalid-selector")
    for request in (
        ReportRequest(
            target_id=fixture_graph.evaluation_id,
            target_kind="evaluation",
            evaluation_id="another-evaluation",
        ),
        ReportRequest(
            target_id=fixture_graph.comparison_id,
            target_kind="comparison",
            result_snapshot_id="another-result",
        ),
    ):
        with pytest.raises(ServiceFailure) as failure:
            service.create(request, operation_id=f"invalid-{request.target_kind}")
        assert failure.value.error.reason == "invalid_report_selector"
    assert source.commit_calls == 0

    collision_key = ResourceKey("evaluations", fixture_graph.run_id)
    source.records[collision_key] = StoredRecord(collision_key, b"collision", "collision")
    with pytest.raises(ServiceFailure) as collision:
        service.create(
            ReportRequest(target_id=fixture_graph.run_id),
            operation_id="report-ambiguous-target",
        )
    assert collision.value.error.reason == "ambiguous_report_target"
    assert source.commit_calls == 0


def test_file_project_report_export_writes_rendered_bytes_after_source_read(
    fixture_graph: FixtureGraph, tmp_path: Path
) -> None:
    clock = SystemClock()
    project_root = tmp_path / "copied authored fixture"
    shutil.copytree(fixture_graph.root, project_root)

    class BoundaryTrackingSource:
        def __init__(self, inner: FileProjectSource) -> None:
            self.inner = inner
            self.active_boundaries = 0

        @contextmanager
        def consistent_read(self):
            self.active_boundaries += 1
            try:
                with self.inner.consistent_read():
                    yield self
            finally:
                self.active_boundaries -= 1

        def capture_snapshot(self, keys=None):
            return self.inner.capture_snapshot(keys)

        def operation_receipt(self, operation_id, *, intent_hash):
            return self.inner.operation_receipt(operation_id, intent_hash=intent_hash)

        def commit(self, operation_id, changes, *, intent_hash=None):
            return self.inner.commit(operation_id, changes, intent_hash=intent_hash)

    with FileProjectSource(project_root) as source:
        tracked = BoundaryTrackingSource(source)
        report = ReportService(tracked, clock, lambda: "report-file").create(
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
                assert tracked.active_boundaries == 0
                return NativeArtifactWriter().write(path, body, display_is_safe=display_is_safe)

        writer = NativeArtifactWriter(protected_project_roots=(project_root,))
        blocked = ReportService(tracked, clock).export(
            report.record.id,
            format="json",
            destination=str(project_root / "source" / "blocked.json"),
            writer=writer,
        )
        assert blocked.success is False
        assert blocked.error is not None
        assert blocked.error.reason == "export_destination_unsafe"
        outcome = ReportService(tracked, clock).export(
            report.record.id,
            format="json",
            destination=str(destination),
            writer=SourceProbingWriter(),
        )
        expected = ReportService(tracked, clock).render(report.record.id, format="json")
        assert outcome.success is True
        assert blocked.report.report_id == outcome.report.report_id == report.record.id
        assert (
            blocked.report.content_hash == outcome.report.content_hash == report.record.content_hash
        )
        assert destination.read_bytes() == expected.body
        assert outcome.artifact_hash == expected.bytes_hash
        assert source.read(ResourceKey("reports", report.record.id)) is not None
