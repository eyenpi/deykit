"""Focused report behavior over one reusable saved fixture evidence graph."""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

import deykit.application.reports as reports_module
from deykit.application.checks import CheckRequest, CheckService, check_snapshot_from_records
from deykit.application.comparisons import ComparisonService
from deykit.application.demo import DemoService
from deykit.application.diagnostics import (
    ChoiceOrderRequest,
    DiagnosticService,
    diagnostic_snapshot_from_records,
)
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService, evaluation_hash
from deykit.application.execution import ExecutionService
from deykit.application.fixtures import FixtureService
from deykit.application.labels import LabelService
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.application.reports import ReportService, admit_report_from_records
from deykit.cli.context import SystemClock
from deykit.contracts.artifacts import ArtifactWriteOutcome
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.execution_groups import (
    CheckSnapshot,
    DiagnosticSnapshot,
    ExecutionGroup,
)
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.ports import (
    ChoiceCompiler,
    CommitReceipt,
    ProviderTransport,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    ComparisonRecord,
    CompiledRequest,
    DispatchOutcome,
    EvaluationRecord,
    FixtureBinding,
    NormalizedAnswer,
    PreparedCase,
    ProviderProfile,
    RegressionRecord,
    ReportRecord,
    ResultSnapshot,
    RunManifest,
)
from deykit.contracts.redaction import Sanitizer
from deykit.contracts.report_json import REPORT_ARTIFACT_MAX_BYTES, REPORT_CONTENT_LIMITS
from deykit.diagnostics.orders import choice_orders
from deykit.providers.choice import JevChoiceCompiler
from deykit.regressions.evidence import regression_hash
from deykit.reports.admission import ReportAdmissionError, admit_report, report_hash
from deykit.reports.group_projection import _selection
from deykit.reports.models import (
    RawChoices,
    RawMaterial,
    ReportContent,
    ReportRequest,
    ReportView,
)
from deykit.reports.projection import (
    _admit_evaluation_metrics,
    project_json_source,
    project_opaque_response_bytes,
)
from deykit.reports.render import render_content
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.runner.ports import Backend, BackendFactory
from deykit.storage import FileProjectSource
from deykit.storage.artifact_export import NativeArtifactWriter
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


@dataclass(frozen=True)
class FixtureGraph:
    root: Path
    run_id: str
    evaluation_id: str
    reevaluation_id: str
    comparison_id: str
    records: tuple[StoredRecord, ...]


@dataclass(frozen=True)
class GroupReportGraph:
    """One authored native project with partial and resumed P12 group snapshots."""

    root: Path
    records: tuple[StoredRecord, ...]
    diagnostic_group_id: str
    diagnostic_partial_snapshot_id: str
    diagnostic_complete_snapshot_id: str
    check_group_id: str
    check_partial_snapshot_id: str
    check_complete_snapshot_id: str
    regression_ids: tuple[str, ...]
    case_ids: tuple[str, ...]
    reused_saved_graph: bool
    lifecycle_reports_created_before_resume: bool


_GROUP_FIXTURE_ID = "m03-group-report-fixtures-v2"
_GROUP_FIXTURE_OPERATION = "m03groupv2-fixtures-create"
_DIAGNOSTIC_GROUP_OPERATION = "m03groupv2-diagnostic-start"
_DIAGNOSTIC_RESUME_OPERATION = "m03groupv2-diagnostic-resume"
_CHECK_GROUP_OPERATION = "m03groupv2-check-start"
_CHECK_RESUME_OPERATION = "m03groupv2-check-resume"
_DIAGNOSTIC_REPORT_ID = "group-diagnostic-v2-initial-report"
_DIAGNOSTIC_REPORT_OPERATION = "m03groupv2-diagnostic-report-create"
_CHECK_REPORT_ID = "group-check-v2-initial-report"
_CHECK_REPORT_OPERATION = "m03groupv2-check-report-create"


class ReplayGuardClock:
    def utc_now(self) -> str:
        raise AssertionError("report replay must not ask for time")

    def monotonic(self) -> float:
        raise AssertionError("report replay must not ask for monotonic time")


def _replay_guard_id() -> str:
    raise AssertionError("report replay must not allocate an ID")


class UnknownOnceBackends(BackendFactory):
    """Wrap local fixture transports with one controlled unknown dispatch."""

    def __init__(self, source: FileProjectSource, clock: SystemClock) -> None:
        self.inner = ProviderBackends(source, clock)
        self.unknown_case_id: str | None = None
        self.unknown_delivered = False

    def profile(self, provider_id: str | None, fixture_set_id: str | None) -> ProviderProfile:
        return self.inner.profile(provider_id, fixture_set_id)

    def profile_captured(
        self,
        provider_id: str | None,
        fixture_set_id: str | None,
        records: tuple[StoredRecord, ...],
    ) -> ProviderProfile:
        return self.inner.profile_captured(provider_id, fixture_set_id, records)

    def resolve(self, profile: ProviderProfile, fixture_set_id: str | None) -> Backend:
        backend = self.inner.resolve(profile, fixture_set_id)
        return self._controlled(backend)

    def resolve_captured(
        self,
        profile: ProviderProfile,
        fixture_set_id: str | None,
        records: tuple[StoredRecord, ...],
    ) -> Backend:
        return self._controlled(self.inner.resolve_captured(profile, fixture_set_id, records))

    def _controlled(self, backend: Backend) -> Backend:
        parent = self

        class ControlledBackend:
            @property
            def compiler(self) -> ChoiceCompiler:
                return backend.compiler

            def preflight(
                self,
                decision_id: str,
                dataset_id: str,
                definition: ChoiceDefinition | None = None,
            ) -> ServiceError | None:
                return backend.preflight(decision_id, dataset_id, definition)

            def for_case(self, case_id: str) -> ProviderTransport:
                transport = backend.for_case(case_id)

                class ControlledTransport:
                    async def dispatch(
                        self, request: CompiledRequest, *, timeout_seconds: float
                    ) -> DispatchOutcome:
                        if parent.unknown_case_id == case_id and not parent.unknown_delivered:
                            parent.unknown_delivered = True
                            return DispatchOutcome(
                                state="unknown",
                                error=ServiceError(code="provider_rejected", reason="timeout"),
                            )
                        return await transport.dispatch(request, timeout_seconds=timeout_seconds)

                return ControlledTransport()

        return ControlledBackend()


def build_group_report_graph(
    fixture_graph: FixtureGraph, tmp_path_factory: pytest.TempPathFactory
) -> GroupReportGraph:
    """Build once, or reuse DEYKIT_TEST_REPORT_GROUP_PROJECT from a prior authored run."""
    configured_root = os.environ.get("DEYKIT_TEST_REPORT_GROUP_PROJECT")
    root = (
        Path(configured_root).resolve()
        if configured_root is not None
        else tmp_path_factory.mktemp("saved-group-report-project") / "Deykit Fixture"
    )
    if not (root / "deykit.project.json").exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(fixture_graph.root, root, dirs_exist_ok=True)

    with FileProjectSource(root) as source:
        records = source.capture_snapshot()
        groups = tuple(
            load_record(ExecutionGroup, item.body)
            for item in records
            if item.key.collection == "execution_groups"
        )
        diagnostic_group = next(
            (
                item
                for item in groups
                if item.kind == "choice_order" and item.operation_id == _DIAGNOSTIC_GROUP_OPERATION
            ),
            None,
        )
        check_group = next(
            (
                item
                for item in groups
                if item.kind == "regression_check" and item.operation_id == _CHECK_GROUP_OPERATION
            ),
            None,
        )
        diagnostic_snapshots = tuple(
            load_record(DiagnosticSnapshot, item.body)
            for item in records
            if item.key.collection == "diagnostic_snapshots"
        )
        check_snapshots = tuple(
            load_record(CheckSnapshot, item.body)
            for item in records
            if item.key.collection == "check_snapshots"
        )

        if diagnostic_group is not None and check_group is not None:
            diagnostic_history = sorted(
                (item for item in diagnostic_snapshots if item.group_id == diagnostic_group.id),
                key=lambda item: item.sequence,
            )
            check_history = sorted(
                (item for item in check_snapshots if item.group_id == check_group.id),
                key=lambda item: item.sequence,
            )
            assert len(diagnostic_history) >= 2 and len(check_history) >= 2
            check_member = check_group
            regression_ids = tuple(
                regression_id
                for member in check_member.members
                for regression_id in load_record(
                    RunManifest,
                    next(
                        stored.body
                        for stored in records
                        if stored.key == ResourceKey("runs", member.run_id)
                    ),
                ).regression_ids
            )
            case_ids = tuple(
                load_record(RegressionRecord, item.body).case_id
                for item in records
                if item.key.collection == "regressions" and item.key.resource_id in regression_ids
            )
            assert len(regression_ids) == 2 and len(set(case_ids)) == 2
            reports = {
                item.key.resource_id: load_record(ReportRecord, item.body)
                for item in records
                if item.key.collection == "reports"
            }
            diagnostic_report = reports.get(_DIAGNOSTIC_REPORT_ID)
            check_report = reports.get(_CHECK_REPORT_ID)
            lifecycle_reports_saved = (
                diagnostic_report is not None
                and diagnostic_report.diagnostic_snapshot_id == diagnostic_history[0].id
                and check_report is not None
                and check_report.check_snapshot_id == check_history[0].id
            )
            return GroupReportGraph(
                root,
                records,
                diagnostic_group.id,
                diagnostic_history[0].id,
                diagnostic_history[-1].id,
                check_group.id,
                check_history[0].id,
                check_history[-1].id,
                regression_ids,
                case_ids,
                True,
                lifecycle_reports_saved,
            )

        failed_diagnostic_group = next(
            (item for item in groups if item.kind == "choice_order"), None
        )
        base_manifest = load_record(
            RunManifest,
            next(
                item.body
                for item in records
                if item.key == ResourceKey("runs", fixture_graph.run_id)
            ),
        )
        base_snapshots = tuple(
            load_record(ResultSnapshot, item.body)
            for item in records
            if item.key.collection == "result_snapshots"
            and load_record(ResultSnapshot, item.body).run_id == fixture_graph.run_id
        )
        base_snapshot = max(
            base_snapshots,
            key=lambda item: (item.through_event_sequence, item.created_at, item.id),
        )
        valid_case_ids = tuple(
            item.case_id for item in base_snapshot.results if item.status == "valid"
        )
        assert len(valid_case_ids) >= 2
        assert base_manifest.decision_id is not None
        assert base_manifest.dataset_id is not None
        assert base_manifest.fixture_set_id is not None
        assert base_manifest.decision_revision_id is not None
        clock = SystemClock()
        backends = UnknownOnceBackends(source, clock)
        execution = ExecutionService(source, source, backends, clock)
        diagnostic_service = DiagnosticService(execution)
        prepared_requests: list[tuple[str, CompiledRequest]] = []
        if failed_diagnostic_group is not None:
            failed_manifests = tuple(
                load_record(
                    RunManifest,
                    next(
                        item.body
                        for item in records
                        if item.key == ResourceKey("runs", member.run_id)
                    ),
                )
                for member in failed_diagnostic_group.members
            )
            selected_case_ids = failed_manifests[0].case_ids
            assert len(selected_case_ids) == 2
            assert all(item.case_ids == selected_case_ids for item in failed_manifests)
            for member in failed_diagnostic_group.members:
                for case_id in selected_case_ids:
                    prepared = load_record(
                        PreparedCase,
                        next(
                            item.body
                            for item in records
                            if item.key == ResourceKey("prepared_cases", case_id, (member.run_id,))
                        ),
                    )
                    assert prepared.request is not None
                    prepared_requests.append((case_id, prepared.request))
        else:
            selected_case_ids = valid_case_ids[:2]
            original_run_request = RunRequest(
                decision_id=base_manifest.decision_id,
                dataset_id=base_manifest.dataset_id,
                mode="fixture",
                fixture_set_id=base_manifest.fixture_set_id,
                revision_id=base_manifest.decision_revision_id,
                case_ids=selected_case_ids,
                settings=base_manifest.settings,
            )
            for plan in execution.planner.prepare_orders(original_run_request, orders=2, seed=19):
                prepared_requests.extend(
                    (item.case_id, item.request)
                    for item in plan.prepared
                    if item.request is not None
                )
        assert len(prepared_requests) == 4
        assert all(
            len({request.body_hash for case, request in prepared_requests if case == case_id}) == 2
            for case_id in selected_case_ids
        )
        fixture_service = FixtureService(source, clock)
        original_fixture = fixture_service.read(base_manifest.fixture_set_id).fixture_set
        authored_by_case = {
            item.case_id: item for item in original_fixture.bindings if item.answer is not None
        }
        bindings = tuple(
            FixtureBinding(
                id=f"m03-{case_id}-{request.body_hash[:16]}",
                case_id=case_id,
                request=request,
                answer=authored_by_case[case_id].answer,
            )
            for case_id, request in prepared_requests
            if case_id in authored_by_case
        )
        assert len(bindings) == 4
        group_fixture = fixture_service.create(
            _GROUP_FIXTURE_ID,
            base_manifest.decision_id,
            base_manifest.dataset_id,
            "M03 authored option-order report fixture",
            original_fixture.model_identity,
            tuple(dump_record(item) for item in bindings),
            operation_id=_GROUP_FIXTURE_OPERATION,
            note=(
                "Binds exact saved compiler requests for both option orders; answers are copied "
                "from the original authored fixture."
            ),
        )
        run_request = RunRequest(
            decision_id=base_manifest.decision_id,
            dataset_id=base_manifest.dataset_id,
            mode="fixture",
            fixture_set_id=group_fixture.fixture_set.id,
            revision_id=base_manifest.decision_revision_id,
            case_ids=selected_case_ids,
            settings=base_manifest.settings,
        )
        backends.unknown_case_id = selected_case_ids[0]
        initial_diagnostic = asyncio.run(
            diagnostic_service.start(
                ChoiceOrderRequest(
                    run=run_request,
                    orders=2,
                    seed=19,
                ),
                operation_id=_DIAGNOSTIC_GROUP_OPERATION,
            )
        )
        assert initial_diagnostic.group.snapshot_id is not None
        diagnostic_partial_id = initial_diagnostic.group.snapshot_id
        partial_records = source.capture_snapshot()
        partial_diagnostic = diagnostic_snapshot_from_records(
            partial_records, diagnostic_partial_id
        )
        assert partial_diagnostic.summary.fully_observed_case_count == 1
        diagnostic_history_request = ReportRequest(
            target_id=initial_diagnostic.group.group_id,
            target_kind="diagnostic",
            group_snapshot_id=diagnostic_partial_id,
        )
        diagnostic_history_service = ReportService(source, clock, lambda: _DIAGNOSTIC_REPORT_ID)
        diagnostic_history_report = diagnostic_history_service.create(
            diagnostic_history_request,
            operation_id=_DIAGNOSTIC_REPORT_OPERATION,
        )
        diagnostic_history_hash = diagnostic_history_report.record.content_hash
        diagnostic_history_json = diagnostic_history_service.render(
            diagnostic_history_report.record.id, format="json"
        ).body
        diagnostic_history_markdown = diagnostic_history_service.render(
            diagnostic_history_report.record.id, format="markdown"
        ).body
        backends.unknown_delivered = True
        completed_diagnostic = asyncio.run(
            diagnostic_service.resume(
                initial_diagnostic.group.group_id,
                operation_id=_DIAGNOSTIC_RESUME_OPERATION,
                retry_unknown=True,
            )
        )
        assert completed_diagnostic.group.snapshot_id is not None

        completed_diagnostic_snapshot = diagnostic_snapshot_from_records(
            source.capture_snapshot(), completed_diagnostic.group.snapshot_id
        )
        source_member = completed_diagnostic_snapshot.members[0]
        result_by_case = {item.case_id: item for item in source_member.results.results}
        revision = source_member.revision
        option_ids = tuple(option.id for option in revision.definition.questions[0].options)
        regression_service = RegressionService(source, clock)
        regressions = []
        for index, case_id in enumerate(selected_case_ids):
            answer = result_by_case.get(case_id)
            expected = answer.answer.option_id if answer and answer.answer else option_ids[0]
            if index == 1:
                expected = next(option for option in option_ids if option != expected)
            regressions.append(
                regression_service.add(
                    RegressionAdd(
                        run_id=source_member.manifest.id,
                        case_id=case_id,
                        acceptable_option_ids=(expected,),
                        reason=f"Authored group oracle {index}",
                        result_snapshot_id=source_member.results.id,
                        provenance="authored_fixture",
                    ),
                    operation_id=f"m03groupv2-regression-{index}",
                )
            )
        check_service = CheckService(execution)
        backends.unknown_case_id = selected_case_ids[1]
        backends.unknown_delivered = False
        initial_check = asyncio.run(
            check_service.start(
                CheckRequest(
                    decision_id=base_manifest.decision_id,
                    mode="fixture",
                    fixture_set_id=group_fixture.fixture_set.id,
                    regression_ids=tuple(item.id for item in regressions),
                    settings=base_manifest.settings,
                ),
                operation_id=_CHECK_GROUP_OPERATION,
            )
        )
        assert initial_check.group.snapshot_id is not None
        partial_check_id = initial_check.group.snapshot_id
        partial_check = check_snapshot_from_records(source.capture_snapshot(), partial_check_id)
        assert {item.passed for item in partial_check.cases} == {True, None}
        assert next(item for item in partial_check.cases if item.passed is None).status == "unknown"
        check_history_request = ReportRequest(
            target_id=initial_check.group.group_id,
            target_kind="check",
            group_snapshot_id=partial_check_id,
        )
        check_history_service = ReportService(source, clock, lambda: _CHECK_REPORT_ID)
        check_history_report = check_history_service.create(
            check_history_request,
            operation_id=_CHECK_REPORT_OPERATION,
        )
        check_history_hash = check_history_report.record.content_hash
        check_history_json = check_history_service.render(
            check_history_report.record.id, format="json"
        ).body
        check_history_markdown = check_history_service.render(
            check_history_report.record.id, format="markdown"
        ).body
        backends.unknown_delivered = True
        completed_check = asyncio.run(
            check_service.resume(
                initial_check.group.group_id,
                operation_id=_CHECK_RESUME_OPERATION,
                retry_unknown=True,
            )
        )
        assert completed_check.group.snapshot_id is not None
        records = source.capture_snapshot()
        for history_service, history_report, expected_hash, expected_json, expected_markdown in (
            (
                diagnostic_history_service,
                diagnostic_history_report,
                diagnostic_history_hash,
                diagnostic_history_json,
                diagnostic_history_markdown,
            ),
            (
                check_history_service,
                check_history_report,
                check_history_hash,
                check_history_json,
                check_history_markdown,
            ),
        ):
            assert (
                history_service.read(history_report.record.id).record.content_hash == expected_hash
            )
            assert (
                history_service.render(history_report.record.id, format="json").body
                == expected_json
            )
            assert (
                history_service.render(history_report.record.id, format="markdown").body
                == expected_markdown
            )
        diagnostic_replay = ReportService(source, ReplayGuardClock(), _replay_guard_id).create(
            diagnostic_history_request,
            operation_id=_DIAGNOSTIC_REPORT_OPERATION,
        )
        check_replay = ReportService(source, ReplayGuardClock(), _replay_guard_id).create(
            check_history_request,
            operation_id=_CHECK_REPORT_OPERATION,
        )
        assert (
            diagnostic_replay.replayed
            and diagnostic_replay.record.content_hash == diagnostic_history_hash
        )
        assert check_replay.replayed and check_replay.record.content_hash == check_history_hash
        return GroupReportGraph(
            root,
            records,
            initial_diagnostic.group.group_id,
            diagnostic_partial_id,
            completed_diagnostic.group.snapshot_id,
            initial_check.group.group_id,
            partial_check_id,
            completed_check.group.snapshot_id,
            tuple(item.id for item in regressions),
            selected_case_ids,
            False,
            True,
        )


def build_fixture_graph(tmp_path_factory: pytest.TempPathFactory) -> FixtureGraph:
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
        lambda path, create: FileProjectSource(path, create=create),
        clock,
        staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
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


@pytest.mark.parametrize("count", [100, 1000, 10**20, 10**30 + 1000])
def test_metrics_projection_preserves_exact_exponent_counts(
    fixture_graph: FixtureGraph, count: int
) -> None:
    record = next(
        item
        for item in fixture_graph.records
        if item.key == ResourceKey("evaluations", fixture_graph.evaluation_id)
    )
    evaluation = load_record(EvaluationRecord, record.body)
    metrics = parse_json(evaluation.metrics_source)
    assert isinstance(metrics, dict)
    baseline = metrics["baseline"]
    assert isinstance(baseline, dict)
    baseline["fit_support"] = count
    source = dump_json(metrics)
    assert f'"fit_support":{count}' not in source
    projected = _admit_evaluation_metrics(source)
    assert type(projected.baseline.fit_support) is int
    assert projected.baseline.fit_support == count


@pytest.mark.parametrize(
    "count",
    [Decimal("100.5"), Decimal("100.000000000000000000000000001"), True, "100", -100],
)
def test_metrics_projection_rejects_noninteger_or_invalid_counts(
    fixture_graph: FixtureGraph, count
) -> None:
    record = next(
        item
        for item in fixture_graph.records
        if item.key == ResourceKey("evaluations", fixture_graph.evaluation_id)
    )
    evaluation = load_record(EvaluationRecord, record.body)
    metrics = parse_json(evaluation.metrics_source)
    assert isinstance(metrics, dict)
    baseline = metrics["baseline"]
    assert isinstance(baseline, dict)
    baseline["fit_support"] = count
    with pytest.raises(ServiceFailure) as error:
        _admit_evaluation_metrics(dump_json(metrics))
    assert error.value.error.reason == "report_metrics_mismatch"


@pytest.mark.parametrize("version", ["1", "1.0", "1e0", "true", '"1"'])
def test_metrics_projection_preserves_strict_explicit_record_version(
    fixture_graph: FixtureGraph, version: str
) -> None:
    record = next(
        item
        for item in fixture_graph.records
        if item.key == ResourceKey("evaluations", fixture_graph.evaluation_id)
    )
    evaluation = load_record(EvaluationRecord, record.body)
    source = evaluation.metrics_source[:-1] + ',"schema_version":' + version + "}"
    if version == "1":
        assert _admit_evaluation_metrics(source).schema_version == 1
        return
    with pytest.raises(ServiceFailure) as error:
        _admit_evaluation_metrics(source)
    assert error.value.error.reason == "report_metrics_mismatch"


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

    stored_report = source.records[ResourceKey("reports", report.record.id)]
    captured = tuple(source.records.values())
    assert admit_report_from_records(stored_report, captured) == report
    assert service._admit_captured_report(stored_report, captured) == report

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
        b"authored\\_fixture\\_not\\_provider\\_quality"
        in service.render(report.record.id, format="markdown").body
    )
    markdown = service.render(report.record.id, format="markdown").body.decode("utf-8")
    for fragment in (
        "- Fitting support: 9; excluded acceptable sets:",
        "- Evaluation snapshots: `",
        "- Evaluation splits:",
        "- Selected: 12; scoring population: provider\\_valid\\_applicable\\_labels; scored:",
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
    evaluation_markdown = comparison_markdown.split("## Comparison", maxsplit=1)[0]
    assert (
        evaluation_markdown.index("### Class metrics")
        < evaluation_markdown.index("### Confusion matrix")
        < evaluation_markdown.index("### Baseline")
        < evaluation_markdown.index("### Latency and usage")
        < evaluation_markdown.rindex("### Case outcomes")
        < comparison_markdown.index("## Comparison")
        < comparison_markdown.index("## Explicitly included raw material")
    )


def test_report_admission_rejects_rehashed_context_and_missing_persisted_version(
    fixture_graph: FixtureGraph,
) -> None:
    for mutation in ("context", "metric", "content-version", "metrics-version"):
        source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
        evaluation_key = ResourceKey("evaluations", fixture_graph.evaluation_id)
        original_evaluation = source.records[evaluation_key]
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
        elif mutation == "metric":
            tree = parse_json(view.record.content_source)
            assert isinstance(tree, dict)
            evaluations = tree["evaluations"]
            assert isinstance(evaluations, list)
            metrics = evaluations[0]["metrics"]
            assert isinstance(metrics, dict)
            baseline = metrics["baseline"]
            assert isinstance(baseline, dict)
            assert baseline["fit_support"] == 9
            baseline["fit_support"] = 8
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
        assert source.records[evaluation_key] == original_evaluation


def test_rehashed_comparison_context_copy_cannot_change_linked_evidence(
    fixture_graph: FixtureGraph,
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    comparison_key = ResourceKey("comparisons", fixture_graph.comparison_id)
    original_comparison = source.records[comparison_key]
    service = ReportService(source, SystemClock(), lambda: "report-comparison-copy")
    view = service.create(
        ReportRequest(target_id=fixture_graph.comparison_id, target_kind="comparison"),
        operation_id="report-comparison-copy-create",
    )
    tree = parse_json(view.record.content_source)
    assert isinstance(tree, dict)
    comparison = tree["comparison"]
    assert isinstance(comparison, dict)
    left = comparison["left"]
    assert isinstance(left, dict)
    left["requested_model"] = "forged-model"
    changed = view.record.model_copy(update={"content_source": dump_json(tree)})
    changed = changed.model_copy(update={"content_hash": report_hash(changed, view.content)})
    body = dump_record(changed)
    key = ResourceKey("reports", view.record.id)
    source.records[key] = StoredRecord(key, body, bytes_hash(body))

    with pytest.raises(ServiceFailure) as failure:
        service.read(view.record.id)
    assert failure.value.error.code == "incompatible_data"
    assert failure.value.error.reason == "report_link_mismatch"
    assert source.records[comparison_key] == original_comparison


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
        "````\ntrusted payload ```\n# injected heading\nnext\n````\n"
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

    oversized = raw.model_copy(update={"source": "x" * REPORT_ARTIFACT_MAX_BYTES})
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


@pytest.mark.parametrize("bound", ["content", "escaped_record"])
def test_report_content_limit_fails_before_memory_source_write(
    fixture_graph: FixtureGraph, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    original_project = reports_module.project_evaluation

    def oversized_projection(*args, **kwargs):
        projected, materials = original_project(*args, **kwargs)
        case_id = projected.cases[0].case_id
        large_source = (
            "x" * REPORT_CONTENT_LIMITS.max_bytes if bound == "content" else '"' * 10_600_000
        )
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
        assert blocked.error.reason == "export_destination_protected"
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


def _group_report_request(
    graph: GroupReportGraph,
    kind: Literal["diagnostic", "check"],
    snapshot_id: str,
    *,
    raw: RawChoices | None = None,
) -> ReportRequest:
    group_id = graph.diagnostic_group_id if kind == "diagnostic" else graph.check_group_id
    return ReportRequest(
        target_id=group_id,
        target_kind=kind,
        group_snapshot_id=snapshot_id,
        raw=raw or RawChoices(),
    )


def test_group_reports_bind_historical_partial_and_latest_resumed_snapshots(
    group_report_graph: GroupReportGraph,
) -> None:
    graph = group_report_graph
    all_records = graph.records
    diagnostic_partial = diagnostic_snapshot_from_records(
        all_records, graph.diagnostic_partial_snapshot_id
    )
    selection_source = parse_json(diagnostic_partial.group.selection_source)
    assert isinstance(selection_source, dict)
    selection_request = selection_source.get("request")
    assert isinstance(selection_request, dict)
    selection_run = selection_request.get("run")
    assert isinstance(selection_run, dict)
    selection_settings = selection_run.get("settings")
    assert isinstance(selection_settings, dict)
    selection_settings["max_attempts"] = Decimal(100)
    selection_request.pop("seed", None)
    selection_request["orders"] = 4
    selection_text = dump_json(selection_source)
    assert '"max_attempts":1e2' in selection_text
    selection_snapshot = replace(
        diagnostic_partial,
        group=diagnostic_partial.group.model_copy(update={"selection_source": selection_text}),
    )
    two_option_definition = ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose one of two options.",
                options=(
                    ChoiceOption(id="accept", name="Accept"),
                    ChoiceOption(id="review", name="Review"),
                ),
            ),
        ),
    )
    two_option_revision = diagnostic_partial.members[0].revision.model_copy(
        update={"definition": two_option_definition}
    )
    expected_orders = choice_orders(("accept", "review"), orders=4, seed=0)
    assert len(expected_orders) == 2
    projected_members = tuple(
        replace(
            member,
            revision=two_option_revision,
            manifest=member.manifest.model_copy(update={"option_order": option_order}),
        )
        for member, option_order in zip(
            diagnostic_partial.members[:2], expected_orders, strict=True
        )
    )
    deduplicated_snapshot = replace(selection_snapshot, members=projected_members)
    seed, algorithm, option_orders = _selection(deduplicated_snapshot)
    assert seed == 0
    assert algorithm == "deykit-choice-order-v1"
    assert option_orders == expected_orders
    first_order = projected_members[0].manifest.option_order
    assert first_order is not None
    duplicate_member = replace(
        projected_members[1],
        manifest=projected_members[1].manifest.model_copy(update={"option_order": first_order}),
    )
    inconsistent = replace(
        deduplicated_snapshot,
        members=(projected_members[0], duplicate_member),
    )
    with pytest.raises(ServiceFailure) as inconsistent_selection:
        _selection(inconsistent)
    assert inconsistent_selection.value.error.reason == "report_group_selection_mismatch"
    diagnostic_latest = diagnostic_snapshot_from_records(
        all_records, graph.diagnostic_complete_snapshot_id
    )
    assert diagnostic_partial.summary.independent_case_count == 2
    assert diagnostic_partial.summary.order_count == 2
    assert diagnostic_partial.summary.expanded_result_count == 4
    assert diagnostic_partial.summary.fully_observed_case_count == 1
    assert diagnostic_partial.summary.disagreement.numerator == 0
    assert diagnostic_partial.summary.disagreement.denominator == 1
    assert diagnostic_latest.summary.fully_observed_case_count == 2
    check_partial = check_snapshot_from_records(all_records, graph.check_partial_snapshot_id)
    check_latest = check_snapshot_from_records(all_records, graph.check_complete_snapshot_id)
    assert {item.passed for item in check_partial.cases} == {True, None}
    assert next(item for item in check_partial.cases if item.passed is None).status == "unknown"
    assert {item.passed for item in check_latest.cases} == {True, False}
    assert tuple(item.content_hash for item in check_latest.regressions) == tuple(
        item.content_hash for item in check_partial.regressions
    )

    # The session graph also created these reports before each real resume.
    if not graph.reused_saved_graph:
        assert graph.lifecycle_reports_created_before_resume
    source = MemorySnapshotSource.from_records(all_records)
    clock = SystemClock()
    history_ids = iter(
        (
            "group-history-report",
            "group-history-latest-diagnostic",
            "group-history-latest-check",
        )
    )
    service = ReportService(source, clock, lambda: next(history_ids))
    request = _group_report_request(graph, "diagnostic", graph.diagnostic_partial_snapshot_id)
    first = service.create(request, operation_id="group-history-report-create")
    first_json = service.render(first.record.id, format="json").body
    first_markdown = service.render(first.record.id, format="markdown").body
    assert first.record.diagnostic_snapshot_id == graph.diagnostic_partial_snapshot_id
    default_diagnostic = service.create(
        ReportRequest(target_id=graph.diagnostic_group_id, target_kind="diagnostic"),
        operation_id="group-history-latest-diagnostic",
    )
    assert default_diagnostic.record.diagnostic_snapshot_id == graph.diagnostic_complete_snapshot_id
    default_check = service.create(
        ReportRequest(target_id=graph.check_group_id, target_kind="check"),
        operation_id="group-history-latest-check",
    )
    assert default_check.record.check_snapshot_id == graph.check_complete_snapshot_id

    replay = ReportService(source, ReplayGuardClock(), _replay_guard_id).create(
        request, operation_id="group-history-report-create"
    )
    assert replay.replayed is True
    assert replay.record.content_hash == first.record.content_hash
    assert ReportService(source, clock).render(replay.record.id, format="json").body == first_json
    assert (
        ReportService(source, clock).render(replay.record.id, format="markdown").body
        == first_markdown
    )


def test_group_report_admission_normalizes_only_exact_owned_integers(
    group_report_graph: GroupReportGraph,
) -> None:
    graph = group_report_graph
    source = MemorySnapshotSource.from_records(graph.records)
    view = ReportService(source, SystemClock(), lambda: "group-number-admission").create(
        _group_report_request(graph, "diagnostic", graph.diagnostic_partial_snapshot_id),
        operation_id="group-number-admission-create",
    )

    def stored_with_content(content_source: str) -> StoredRecord:
        changed = view.record.model_copy(update={"content_source": content_source})
        changed = changed.model_copy(update={"content_hash": report_hash(changed, view.content)})
        body = dump_record(changed)
        return StoredRecord(ResourceKey("reports", changed.id), body, bytes_hash(body))

    content_tree = parse_json(view.record.content_source)
    assert isinstance(content_tree, dict)
    diagnostic = content_tree.get("diagnostic")
    assert isinstance(diagnostic, dict)
    summary = diagnostic.get("summary")
    assert isinstance(summary, dict)
    diagnostic["max_attempts"] = Decimal(100)
    diagnostic["deadline_seconds"] = Decimal(1000)
    summary["expanded_result_count"] = Decimal(100)
    exponent_source = dump_json(content_tree)
    assert '"max_attempts":1e2' in exponent_source
    assert '"expanded_result_count":1e2' in exponent_source
    admitted = admit_report(stored_with_content(exponent_source))
    assert admitted.content.diagnostic is not None
    assert admitted.content.diagnostic.max_attempts == 100
    assert admitted.content.diagnostic.deadline_seconds == 1000
    assert admitted.content.diagnostic.summary.expanded_result_count == 100

    for value in (Decimal("1.5"), True):
        invalid_tree = parse_json(view.record.content_source)
        assert isinstance(invalid_tree, dict)
        invalid_diagnostic = invalid_tree.get("diagnostic")
        assert isinstance(invalid_diagnostic, dict)
        invalid_diagnostic["max_attempts"] = value
        with pytest.raises(ReportAdmissionError) as failure:
            admit_report(stored_with_content(dump_json(invalid_tree)))
        assert failure.value.reason == "invalid_report_content"

    wrong_version = view.record.content_source.replace(
        '"schema_version":1', '"schema_version":1.0', 1
    )
    with pytest.raises(ReportAdmissionError) as failure:
        admit_report(stored_with_content(wrong_version))
    assert failure.value.reason == "missing_schema_version"


def test_report_admission_preserves_exact_record_version_tokens(
    fixture_graph: FixtureGraph,
) -> None:
    source = MemorySnapshotSource.from_records(snapshot(fixture_graph))
    report_ids = iter(("report-version-run", "report-version-comparison"))
    service = ReportService(source, SystemClock(), lambda: next(report_ids))
    run_report = service.create(
        ReportRequest(target_id=fixture_graph.run_id, target_kind="run"),
        operation_id="report-version-run-create",
    )
    comparison_report = service.create(
        ReportRequest(target_id=fixture_graph.comparison_id, target_kind="comparison"),
        operation_id="report-version-comparison-create",
    )

    def stored_with_source(view: ReportView, content_source: str) -> StoredRecord:
        changed = view.record.model_copy(update={"content_source": content_source})
        changed = changed.model_copy(update={"content_hash": report_hash(changed, view.content)})
        body = dump_record(changed)
        return StoredRecord(ResourceKey("reports", changed.id), body, bytes_hash(body))

    invalid_sources = [
        (
            run_report,
            run_report.record.content_source.replace(
                '{"schema_version":1', '{"schema_version":1e0', 1
            ),
        ),
        (
            run_report,
            run_report.record.content_source.replace(
                '"metrics":{"schema_version":1', '"metrics":{"schema_version":1e0', 1
            ),
        ),
        (
            comparison_report,
            comparison_report.record.content_source.replace(
                '"comparison":{"schema_version":1',
                '"comparison":{"schema_version":1.0',
                1,
            ),
        ),
    ]
    for collection in ("cases", "attempts"):
        tree = parse_json(run_report.record.content_source)
        assert isinstance(tree, dict)
        evaluations = tree.get("evaluations")
        assert isinstance(evaluations, list) and evaluations
        evaluation = evaluations[0]
        assert isinstance(evaluation, dict)
        items = evaluation.get(collection)
        assert isinstance(items, list) and items
        first_item = items[0]
        assert isinstance(first_item, dict)
        first_item["error"] = {"schema_version": 1, "code": "provider_rejected"}
        invalid_version = "1.0" if collection == "cases" else "1e0"
        error_source = dump_json(tree).replace(
            '"error":{"schema_version":1',
            f'"error":{{"schema_version":{invalid_version}',
            1,
        )
        invalid_sources.append((run_report, error_source))

    for view, content_source in invalid_sources:
        with pytest.raises(ReportAdmissionError) as failure:
            admit_report(stored_with_source(view, content_source))
        assert failure.value.reason == "invalid_report_content"


def test_group_raw_switches_cover_all_combinations_with_pinned_lineage(
    group_report_graph: GroupReportGraph,
) -> None:
    graph = group_report_graph
    members = diagnostic_snapshot_from_records(
        graph.records, graph.diagnostic_complete_snapshot_id
    ).members
    for mask in range(8):
        raw = RawChoices(inputs=bool(mask & 1), requests=bool(mask & 2), responses=bool(mask & 4))
        source = MemorySnapshotSource.from_records(graph.records)
        report = ReportService(source, SystemClock(), lambda mask=mask: f"group-raw-{mask}").create(
            _group_report_request(
                graph, "diagnostic", graph.diagnostic_complete_snapshot_id, raw=raw
            ),
            operation_id=f"group-raw-create-{mask}",
        )
        assert report.record.evaluation_ids == ()
        assert report.record.result_snapshot_ids == tuple(member.results.id for member in members)
        assert report.record.label_snapshot_ids == tuple(member.labels.id for member in members)
        expected_categories = {
            category
            for selected, category in (
                (raw.inputs, "input"),
                (raw.requests, "request"),
                (raw.responses, "response"),
            )
            if selected
        }
        assert {item.category for item in report.content.raw_material} == expected_categories
        for item in report.content.raw_material:
            assert item.run_id in {member.manifest.id for member in members}
            assert item.case_id in graph.case_ids
            if item.source is None:
                assert item.unavailable_reason is not None
                assert item.original_hash is None
                assert item.sanitized_hash is None
            else:
                assert item.original_hash is not None
                assert item.encoding is not None
                assert item.sanitized_hash is not None
                assert item.changed_by_redaction is False
            if item.category == "input":
                assert item.identity_kind == "input_semantic_hash"
            elif item.category == "request":
                assert item.identity_kind == "prepared_request_bytes_hash"
            else:
                assert item.identity_kind in {
                    "stored_response_utf8_hash",
                    "stored_response_bytes_hash",
                }


def test_group_report_context_and_regression_lineage_render_before_raw_material(
    group_report_graph: GroupReportGraph,
) -> None:
    graph = group_report_graph
    source = MemorySnapshotSource.from_records(graph.records)
    service = ReportService(source, SystemClock(), lambda: "group-context-report")
    check_report = service.create(
        _group_report_request(
            graph,
            "check",
            graph.check_partial_snapshot_id,
            raw=RawChoices(inputs=True),
        ),
        operation_id="group-context-report-create",
    )
    markdown = service.render(check_report.record.id, format="markdown").body.decode()
    required = (
        "- Requested model:",
        "- Answering models:",
        "- Compiler IDs and version:",
        "- Option order:",
        "- Run:",
        "manifest hash:",
        "- Mode:",
        "Provider profile:",
        "configuration hash:",
        "- Decision:",
        "definition hash:",
        "- Dataset:",
        "- Label snapshot:",
        "- Result snapshot:",
        "event sequence:",
        "- Question:",
        "- Selected cases:",
        "Baseline dataset snapshot:",
        "Baseline label snapshot:",
        "### Regression source lineage",
        "original input hash",
        "source run",
        ", result ",
        ", attempt ",
        "## Frozen source context",
        "## Explicitly included raw material",
    )
    positions = tuple(markdown.index(item) for item in required)
    assert positions == tuple(sorted(positions))
    assert "unavailable" in markdown
    assert check_report.content.check is not None
    assert {item.passed for item in check_report.content.check.cases} == {True, None}
    for case in check_report.content.check.cases:
        assert case.input_hash in markdown
        for source_identity in (
            case.source_run_id,
            case.source_result_snapshot_id,
            case.source_attempt_id,
        ):
            assert (source_identity or "unavailable") in markdown


def test_group_report_creation_never_evaluates_compiles_or_resolves_a_backend(
    group_report_graph: GroupReportGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = group_report_graph
    source = MemorySnapshotSource.from_records(graph.records)
    before_evaluations = tuple(key for key in source.records if key.collection == "evaluations")

    def forbidden(*args, **kwargs):
        pytest.fail("group report creation is read-only over pinned evidence")

    monkeypatch.setattr(EvaluationService, "evaluate_saved", forbidden)
    monkeypatch.setattr(JevChoiceCompiler, "compile", forbidden)
    monkeypatch.setattr(ProviderBackends, "resolve", forbidden)
    report = ReportService(source, SystemClock(), lambda: "group-read-only-report").create(
        _group_report_request(graph, "diagnostic", graph.diagnostic_complete_snapshot_id),
        operation_id="group-read-only-report-create",
    )
    assert report.record.evaluation_ids == ()
    assert (
        tuple(key for key in source.records if key.collection == "evaluations")
        == before_evaluations
    )


def test_group_selectors_cross_binding_and_original_regression_hash_are_enforced(
    group_report_graph: GroupReportGraph,
) -> None:
    graph = group_report_graph
    source = MemorySnapshotSource.from_records(graph.records)
    service = ReportService(source, SystemClock(), lambda: "group-link-report")
    invalid = (
        ReportRequest(
            target_id=graph.diagnostic_group_id,
            target_kind="diagnostic",
            group_snapshot_id=graph.check_partial_snapshot_id,
        ),
        ReportRequest(
            target_id=graph.check_group_id,
            target_kind="check",
            group_snapshot_id=graph.diagnostic_partial_snapshot_id,
        ),
    )
    for index, request in enumerate(invalid):
        with pytest.raises((ServiceFailure, ValidationError)):
            service.create(request, operation_id=f"group-invalid-selector-{index}")
    with pytest.raises(ValidationError):
        ReportRequest(
            target_id=graph.check_group_id,
            target_kind="check",
            group_snapshot_id=graph.check_partial_snapshot_id,
            result_snapshot_id="unrelated-result",
        )
    assert source.commit_calls == 0

    original_key = ResourceKey("regressions", graph.regression_ids[0])
    original = source.records[original_key]
    regression = load_record(RegressionRecord, original.body)
    replacement_reason = regression.reason + " changed"
    service = ReportService(
        source,
        SystemClock(),
        lambda: "group-regression-link-report",
        sanitizer=Sanitizer((regression.reason, replacement_reason)),
    )
    report = service.create(
        _group_report_request(graph, "check", graph.check_complete_snapshot_id),
        operation_id="group-regression-link-create",
    )
    frozen = report.content.check
    assert frozen is not None
    assert any(item.reason == "[REDACTED]" for item in frozen.cases)
    changed = regression.model_copy(update={"reason": replacement_reason, "content_hash": None})
    changed = changed.model_copy(update={"content_hash": regression_hash(changed)})
    changed_body = dump_record(changed)
    source.records[original_key] = StoredRecord(
        original_key, changed_body, bytes_hash(changed_body)
    )
    with pytest.raises(ServiceFailure) as failure:
        service.read(report.record.id)
    assert failure.value.error.reason == "report_link_mismatch"


def test_sensitive_group_and_snapshot_identities_fail_before_commit(
    group_report_graph: GroupReportGraph,
) -> None:
    graph = group_report_graph
    diagnostic_group = load_record(
        ExecutionGroup,
        next(
            item.body
            for item in graph.records
            if item.key == ResourceKey("execution_groups", graph.diagnostic_group_id)
        ),
    )
    diagnostic_snapshot = load_record(
        DiagnosticSnapshot,
        next(
            item.body
            for item in graph.records
            if item.key == ResourceKey("diagnostic_snapshots", graph.diagnostic_partial_snapshot_id)
        ),
    )
    values = (
        (graph.diagnostic_group_id, "diagnostic", graph.diagnostic_partial_snapshot_id),
        (diagnostic_group.content_hash, "diagnostic", graph.diagnostic_partial_snapshot_id),
        (graph.diagnostic_partial_snapshot_id, "diagnostic", graph.diagnostic_partial_snapshot_id),
        (diagnostic_snapshot.content_hash, "diagnostic", graph.diagnostic_partial_snapshot_id),
        (diagnostic_snapshot.segment_id, "diagnostic", graph.diagnostic_partial_snapshot_id),
        (diagnostic_group.members[0].run_id, "diagnostic", graph.diagnostic_partial_snapshot_id),
        (graph.regression_ids[0], "check", graph.check_partial_snapshot_id),
    )
    for index, (value, kind, snapshot_id) in enumerate(values):
        assert value is not None
        source = MemorySnapshotSource.from_records(graph.records)
        service = ReportService(
            source,
            SystemClock(),
            lambda: "group-sensitive-report",
            sanitizer=Sanitizer((value,)),
        )
        with pytest.raises(ServiceFailure) as failure:
            service.create(
                _group_report_request(graph, kind, snapshot_id),
                operation_id=f"group-sensitive-{index}",
            )
        assert failure.value.error.reason == "report_sensitive_identity"
        assert source.commit_calls == 0


def test_file_group_report_export_uses_resumed_saved_graph(
    group_report_graph: GroupReportGraph, tmp_path: Path
) -> None:
    graph = group_report_graph
    project_root = tmp_path / "copied authored group graph"
    shutil.copytree(graph.root, project_root)
    clock = SystemClock()
    with FileProjectSource(project_root) as source:
        report = ReportService(source, clock, lambda: "group-export-report").create(
            _group_report_request(graph, "diagnostic", graph.diagnostic_complete_snapshot_id),
            operation_id="group-export-report-create",
        )
        destination = tmp_path / "diagnostic-group-report.json"
        exported = ReportService(source, clock).export(
            report.record.id,
            format="json",
            destination=str(destination),
            writer=NativeArtifactWriter(protected_project_roots=(project_root,)),
        )
        rendered = ReportService(source, clock).render(report.record.id, format="json")
        assert exported.success is True
        assert destination.read_bytes() == rendered.body
        assert exported.artifact_hash == rendered.bytes_hash
