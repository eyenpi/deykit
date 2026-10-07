"""Bounded ownership, ordering, and historical-exception graph oracles."""

from __future__ import annotations

from deykit.application.errors import ServiceFailure
from deykit.application.project_references import validate_project_references
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.json_value import JsonDocument, bytes_hash
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.records import (
    AttemptEvent,
    CaseRecord,
    CaseResult,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    ComparisonRecord,
    DatasetRecord,
    DatasetSnapshot,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    EvaluationRecord,
    ExecutionSettings,
    LabelSnapshot,
    PreparedCase,
    ProjectRecord,
    ProviderProfile,
    RegressionRecord,
    ReportRecord,
    ResultSnapshot,
    RunEvent,
    RunManifest,
    RunSegment,
)
from deykit.domain.definitions import definition_hash
from deykit.regressions.evidence import regression_hash

STAMP = "2026-10-05T12:00:00Z"


def item(collection: str, resource_id: str, value: object, scope: tuple[str, ...] = ()):
    return StoredRecord(ResourceKey(collection, resource_id, scope), dump_record(value), "0" * 64)


def project() -> StoredRecord:
    return item(
        "project",
        "project",
        ProjectRecord(id="project", name="Project", created_at=STAMP),
    )


def captured_legacy_project() -> tuple[StoredRecord, ...]:
    definition = ChoiceDefinition(
        input_kind="json",
        questions=(
            ChoiceQuestion(
                id="question",
                instructions="Choose an option",
                options=(ChoiceOption(id="yes", name="Yes"), ChoiceOption(id="no", name="No")),
            ),
        ),
    )
    revision = DecisionRevision(
        id="revision",
        decision_id="decision",
        definition=definition,
        content_hash=definition_hash(definition),
        created_at=STAMP,
    )
    dataset_snapshot = DatasetSnapshot(
        id="dataset-snapshot",
        dataset_id="dataset",
        cases=(),
        content_hash=evidence_hash(()),
        created_at=STAMP,
    )
    label_snapshot = LabelSnapshot(
        id="label-snapshot",
        decision_id="decision",
        dataset_snapshot_id=dataset_snapshot.id,
        labels=(),
        content_hash=evidence_hash(()),
        created_at=STAMP,
    )
    run = RunManifest(
        id="legacy-run",
        decision_id=None,
        dataset_id=None,
        provider=None,
        decision_revision_id=revision.id,
        dataset_snapshot_id=dataset_snapshot.id,
        label_snapshot_id=label_snapshot.id,
        provider_profile_id="provider",
        provider_config_hash="0" * 64,
        adapter="fixture",
        compiler_version="not_compiled",
        requested_model="authored-model",
        mode="fixture",
        case_ids=(),
        settings=ExecutionSettings(),
        created_at=STAMP,
        operation_id="legacy-operation",
    )
    records = (
        project(),
        item(
            "decisions",
            "decision",
            DecisionRecord(id="decision", name="Decision", latest_revision_id=revision.id),
        ),
        item(
            "drafts",
            "decision",
            DecisionDraft(decision_id="decision", editor_source="{", updated_at=STAMP),
        ),
        item("revisions", revision.id, revision, ("decision",)),
        item(
            "datasets",
            "dataset",
            DatasetRecord(id="dataset", name="Dataset", created_at=STAMP),
        ),
        item("dataset_snapshots", dataset_snapshot.id, dataset_snapshot),
        item("label_snapshots", label_snapshot.id, label_snapshot),
        item(
            "providers",
            "provider",
            ProviderProfile(
                id="provider",
                adapter="fixture",
                requested_model="authored-model",
                destination="fixture:local",
            ),
        ),
        item("runs", run.id, run),
    )
    return records


def test_duplicate_and_miskeyed_captured_records_fail_before_graph_traversal() -> None:
    project_record = project()
    try:
        validate_project_references((project_record, project_record))
    except ServiceFailure as error:
        assert error.error.reason == "project_reference_duplicate"
    else:
        raise AssertionError("duplicate key was admitted")

    miskeyed = item(
        "datasets", "key-id", DatasetRecord(id="body-id", name="Data", created_at=STAMP)
    )
    try:
        validate_project_references((project_record, miskeyed))
    except ServiceFailure as error:
        assert error.error.reason == "project_reference_wrong_owner"
    else:
        raise AssertionError("miskeyed record was admitted")


def test_orphan_attempt_event_and_foreign_run_segment_are_hard_failures() -> None:
    orphan = item(
        "attempt_events",
        "orphan-event",
        AttemptEvent(
            id="orphan-event",
            attempt_id="missing-attempt",
            sequence=1,
            state="reserved",
            created_at=STAMP,
        ),
        ("missing-attempt",),
    )
    try:
        validate_project_references((project(), orphan))
    except ServiceFailure as error:
        assert error.error.reason == "project_reference_missing"
        assert error.error.resource_id == "orphan-event"
    else:
        raise AssertionError("orphan attempt event was admitted")

    base = captured_legacy_project()
    run_record = next(record for record in base if record.key.collection == "runs")
    run = load_record(RunManifest, run_record.body)
    foreign_run = run.model_copy(update={"id": "foreign-run"})
    segment = RunSegment(
        id="foreign-segment", run_id=foreign_run.id, started_at=STAMP, deadline_at=STAMP
    )
    event = RunEvent(
        id="event",
        run_id=run.id,
        segment_id=segment.id,
        sequence=1,
        state="running",
        created_at=STAMP,
    )
    records = (
        *base,
        item("runs", foreign_run.id, foreign_run),
        item("segments", segment.id, segment, (foreign_run.id,)),
        item("run_events", event.id, event, (run.id,)),
    )
    try:
        validate_project_references(records)
    except ServiceFailure as error:
        assert error.error.reason == "project_reference_wrong_owner"
        assert error.error.resource_id == event.id
    else:
        raise AssertionError("foreign segment link was admitted")


def test_modern_child_cannot_be_hidden_under_incomplete_legacy_run() -> None:
    base = captured_legacy_project()
    run = next(
        load_record(RunManifest, record.body) for record in base if record.key.collection == "runs"
    )
    segment = RunSegment(id="segment", run_id=run.id, started_at=STAMP, deadline_at=STAMP)
    records = (*base, item("segments", segment.id, segment, (run.id,)))

    try:
        validate_project_references(records)
    except ServiceFailure as error:
        assert error.error.reason == "legacy_run_not_executable"
    else:
        raise AssertionError("legacy run with a modern child was downgraded to a warning")


def test_virtual_dataset_ancestry_and_opaque_revision_id_are_historical_values() -> None:
    dataset = DatasetRecord(
        id="dataset",
        revision_id="opaque-revision-from-another-workspace",
        name="Data",
        created_at=STAMP,
    )
    case = CaseRecord(
        id="frozen-case",
        dataset_id=dataset.id,
        input_kind="json",
        input_source='{"text":"frozen"}',
        derived_from=("virtual-parent-not-in-snapshot",),
    )
    snapshot = DatasetSnapshot(
        id="snapshot",
        dataset_id=dataset.id,
        cases=(case,),
        content_hash=evidence_hash((dump_record(case),)),
        created_at=STAMP,
    )

    assert (
        validate_project_references(
            (
                project(),
                item("datasets", dataset.id, dataset),
                item("dataset_snapshots", snapshot.id, snapshot),
            )
        ).warnings
        == ()
    )


def test_unknown_known_report_version_is_not_misclassified_as_legacy_warning() -> None:
    report = ReportRecord(
        id="report",
        evaluation_ids=(),
        result_snapshot_ids=(),
        label_snapshot_ids=(),
        content_source='{"profile":"deykit-report-v1","schema_version":2}',
        content_hash="0" * 64,
        created_at=STAMP,
    )
    try:
        validate_project_references((project(), item("reports", report.id, report)))
    except ServiceFailure as error:
        assert error.error.reason == "missing_schema_version"
    else:
        raise AssertionError("unsupported typed report version became a legacy warning")


def test_typed_report_graph_uses_the_captured_report_reader(monkeypatch) -> None:
    from types import SimpleNamespace

    from deykit.application import project_references

    report = ReportRecord(
        id="report",
        evaluation_ids=(),
        result_snapshot_ids=(),
        label_snapshot_ids=(),
        content_source="{}",
        content_hash="0" * 64,
        created_at=STAMP,
    )
    calls: list[str] = []

    def reject_report(stored, _records):
        calls.append(stored.key.resource_id)
        raise ServiceFailure(
            ServiceError(code="incompatible_data", reason="report_hash_mismatch")
        )

    monkeypatch.setattr(
        project_references,
        "admit_report_metadata",
        lambda _stored: SimpleNamespace(legacy=False),
    )
    monkeypatch.setattr(project_references, "admit_report_from_records", reject_report)

    try:
        validate_project_references((project(), item("reports", report.id, report)))
    except ServiceFailure as error:
        assert error.error.reason == "report_hash_mismatch"
    else:
        raise AssertionError("typed report bypassed captured report admission")
    assert calls == [report.id]


def test_typed_comparison_graph_delegates_to_captured_comparison_reader(monkeypatch) -> None:
    from deykit.application import evaluations, project_references
    from deykit.runner import history

    base = captured_legacy_project()
    legacy_run = next(
        load_record(RunManifest, record.body) for record in base if record.key.collection == "runs"
    )
    provider_record = next(record for record in base if record.key.collection == "providers")
    run = legacy_run.model_copy(
        update={
            "id": "comparison-run",
            "decision_id": "decision",
            "dataset_id": "dataset",
            "baseline_dataset_snapshot_id": "dataset-snapshot",
            "baseline_label_snapshot_id": "label-snapshot",
            "provider": load_record(ProviderProfile, provider_record.body),
        }
    )
    result = ResultSnapshot(
        id="comparison-result",
        run_id=run.id,
        results=(),
        through_event_sequence=0,
        content_hash=evidence_hash(()),
        created_at=STAMP,
    )
    evaluation = EvaluationRecord(
        id="evaluation",
        run_id=run.id,
        result_snapshot_id=result.id,
        label_snapshot_id="label-snapshot",
        mode="original",
        metrics_source="{}",
        content_hash="0" * 64,
        created_at=STAMP,
    )
    comparison = ComparisonRecord(
        id="comparison",
        left_evaluation_id=evaluation.id,
        right_evaluation_id=evaluation.id,
        left_result_snapshot_id=result.id,
        right_result_snapshot_id=result.id,
        outcomes_source="{}",
        content_hash="0" * 64,
        created_at=STAMP,
    )
    calls: list[str] = []
    monkeypatch.setattr(history, "history_from_records", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(evaluations, "admit_evaluation_record", lambda _stored: None)
    monkeypatch.setattr(
        evaluations, "frozen_evaluation_from_records", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        project_references,
        "admit_comparison_from_records",
        lambda stored, _records: calls.append(stored.key.resource_id),
    )
    captured = (
        *base,
        item("runs", run.id, run),
        item("result_snapshots", result.id, result),
        item("evaluations", evaluation.id, evaluation),
        item("comparisons", comparison.id, comparison),
    )

    validate_project_references(captured)

    assert calls == [comparison.id]


def test_hard_error_and_legacy_warning_order_ignore_source_tuple_order() -> None:
    base = captured_legacy_project()
    orphan_a = item(
        "attempt_events",
        "a-orphan",
        AttemptEvent(
            id="a-orphan",
            attempt_id="missing-a",
            sequence=0,
            state="reserved",
            created_at=STAMP,
        ),
    )
    orphan_b = item(
        "attempt_events",
        "b-orphan",
        AttemptEvent(
            id="b-orphan",
            attempt_id="missing-b",
            sequence=0,
            state="reserved",
            created_at=STAMP,
        ),
    )
    shuffled = (base[0], orphan_b, *base[1:], orphan_a)
    ordered = (base[0], orphan_a, *base[1:], orphan_b)
    errors = []
    for records in (ordered, shuffled):
        try:
            validate_project_references(records)
        except ServiceFailure as error:
            errors.append((error.error.reason, error.error.resource_id))
    assert errors == [("project_reference_missing", "a-orphan")] * 2


def test_warning_order_is_stable_after_all_hard_edges_pass() -> None:
    records = captured_legacy_project()
    run = next(
        load_record(RunManifest, record.body)
        for record in records
        if record.key.collection == "runs"
    )
    later = run.model_copy(update={"id": "z-legacy-run"})
    earlier = run.model_copy(update={"id": "a-legacy-run"})
    extras = (item("runs", later.id, later), item("runs", earlier.id, earlier))

    results = (
        validate_project_references((*records, *extras)),
        validate_project_references((*records, *reversed(extras))),
    )

    assert [tuple(error.resource_id for error in result.warnings) for result in results] == [
        ("a-legacy-run", "legacy-run", "z-legacy-run"),
        ("a-legacy-run", "legacy-run", "z-legacy-run"),
    ]


def test_complete_regression_without_attempt_still_enters_origin_admission() -> None:
    records = captured_legacy_project()
    source_run = next(
        load_record(RunManifest, record.body)
        for record in records
        if record.key.collection == "runs"
    )
    provider_record = next(record for record in records if record.key.collection == "providers")
    embedded_provider = load_record(ProviderProfile, provider_record.body)
    source_run = source_run.model_copy(
        update={
            "id": "source-run",
            "decision_id": "decision",
            "dataset_id": "dataset",
            "baseline_dataset_snapshot_id": "dataset-snapshot",
            "baseline_label_snapshot_id": "label-snapshot",
            "provider": embedded_provider,
            "provider_config_hash": bytes_hash(dump_record(embedded_provider)),
            "case_ids": ("removed-case",),
        }
    )
    case = CaseRecord(
        id="removed-case",
        dataset_id="dataset",
        input_kind="json",
        input_source='{"value":"retained"}',
    )
    input_hash = JsonDocument(case.input_source).content_hash
    frozen_dataset = DatasetSnapshot(
        id="dataset-snapshot",
        dataset_id="dataset",
        cases=(case,),
        content_hash=evidence_hash((dump_record(case),)),
        created_at=STAMP,
    )
    prepared = PreparedCase(
        id=case.id,
        run_id=source_run.id,
        case_id=case.id,
        input_hash=input_hash,
        error=ServiceError(code="validation_error", reason="invalid_fixture_input"),
    )
    result_case = CaseResult(
        case_id=case.id,
        input_hash=input_hash,
        status="input_invalid",
        error=prepared.error,
    )
    result = ResultSnapshot(
        id="source-result",
        run_id=source_run.id,
        results=(result_case,),
        through_event_sequence=0,
        content_hash=evidence_hash((result_case.model_dump_json().encode("utf-8"),)),
        created_at=STAMP,
    )
    provisional = RegressionRecord(
        id="regression-no-attempt",
        decision_id="decision",
        source_run_id=source_run.id,
        source_result_snapshot_id=result.id,
        source_attempt_id=None,
        source_case=case,
        provenance="authored_fixture",
        decision_revision_id="revision",
        dataset_id="dataset",
        case_id=case.id,
        question_id="question",
        input_source=case.input_source,
        input_hash=input_hash,
        acceptable_option_ids=("yes",),
        reason="Retained frozen evidence",
        created_at=STAMP,
    )
    regression = provisional.model_copy(update={"content_hash": regression_hash(provisional)})
    captured = (
        *(
            record
            for record in records
            if record.key != ResourceKey("dataset_snapshots", "dataset-snapshot")
            and record.key.collection != "providers"
        ),
        item("dataset_snapshots", frozen_dataset.id, frozen_dataset),
        item("runs", source_run.id, source_run),
        item("prepared_cases", prepared.id, prepared, (source_run.id,)),
        item("result_snapshots", result.id, result),
        item("regressions", regression.id, regression),
    )

    result_view = validate_project_references(captured)

    assert all(warning.resource_id != regression.id for warning in result_view.warnings)


def test_partial_regression_result_link_must_contain_original_case(monkeypatch) -> None:
    from deykit.application import evaluations
    from deykit.runner import history

    records = captured_legacy_project()
    legacy_run = next(
        load_record(RunManifest, record.body)
        for record in records
        if record.key.collection == "runs"
    )
    provider_record = next(record for record in records if record.key.collection == "providers")
    run = legacy_run.model_copy(
        update={
            "id": "partial-run",
            "decision_id": "decision",
            "dataset_id": "dataset",
            "baseline_dataset_snapshot_id": "dataset-snapshot",
            "baseline_label_snapshot_id": "label-snapshot",
            "provider": load_record(ProviderProfile, provider_record.body),
        }
    )
    result = ResultSnapshot(
        id="partial-result",
        run_id=run.id,
        results=(),
        through_event_sequence=0,
        content_hash=evidence_hash(()),
        created_at=STAMP,
    )
    revision = next(
        load_record(DecisionRevision, record.body)
        for record in records
        if record.key.collection == "revisions"
    )
    alternate_revision = DecisionRevision(
        id="alternate-revision",
        decision_id=revision.decision_id,
        definition=revision.definition,
        content_hash=revision.content_hash,
        created_at=STAMP,
    )
    regression = RegressionRecord(
        id="partial-regression",
        decision_revision_id=revision.id,
        dataset_id="dataset",
        source_result_snapshot_id=result.id,
        case_id="removed-case",
        question_id="question",
        input_source='{"value":"removed"}',
        input_hash=JsonDocument('{"value":"removed"}').content_hash,
        acceptable_option_ids=("yes",),
        reason="Partial retained evidence",
        created_at=STAMP,
    )
    monkeypatch.setattr(history, "history_from_records", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        evaluations, "frozen_evaluation_from_records", lambda *_args, **_kwargs: None
    )
    captured = (
        *records,
        item("revisions", alternate_revision.id, alternate_revision, ("decision",)),
        item("runs", run.id, run),
        item("result_snapshots", result.id, result),
        item("regressions", regression.id, regression),
    )

    for value in (
        regression,
        regression.model_copy(update={"decision_revision_id": alternate_revision.id}),
    ):
        variant = tuple(
            item("regressions", value.id, value)
            if record.key.collection == "regressions"
            else record
            for record in captured
        )
        try:
            validate_project_references(variant)
        except ServiceFailure as error:
            assert error.error.reason == "regression_evidence_mismatch"
        else:
            raise AssertionError("partial regression links without matching origin were admitted")
