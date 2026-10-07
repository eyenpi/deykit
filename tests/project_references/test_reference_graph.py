"""Reference edges are checked from a captured batch before semantic admission."""

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.project_references import validate_project_references
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DatasetSnapshot,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    LabelRecord,
    LabelChange,
    ProjectRecord,
    RegressionRecord,
)
from deykit.domain.definitions import definition_hash
from deykit.domain.label_identity import label_id
from deykit.contracts.json_value import JsonDocument
from deykit.regressions.evidence import regression_hash

STAMP = "2026-10-05T12:00:00Z"


def item(collection: str, resource_id: str, value: object, scope: tuple[str, ...] = ()):
    return StoredRecord(
        ResourceKey(collection, resource_id, scope),
        dump_record(value),
        "0" * 64,
    )


def project_record() -> StoredRecord:
    return item(
        "project",
        "project",
        ProjectRecord(id="project", name="Project", created_at=STAMP),
    )


def decision_records(*, latest_revision_id: str | None = None):
    decision = DecisionRecord(id="decision", name="Decision", latest_revision_id=latest_revision_id)
    draft = DecisionDraft(decision_id="decision", editor_source="{", updated_at=STAMP)
    return (
        item("decisions", "decision", decision),
        item("drafts", "decision", draft),
    )


def definition() -> ChoiceDefinition:
    return ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose",
                options=(ChoiceOption(id="yes", name="Yes"), ChoiceOption(id="no", name="No")),
            ),
        ),
    )


def test_dangling_latest_revision_is_a_hard_reference_failure() -> None:
    records = (project_record(), *decision_records(latest_revision_id="missing-revision"))

    with pytest.raises(ServiceFailure) as missing:
        validate_project_references(records)

    assert missing.value.error.reason == "project_reference_missing"
    assert missing.value.error.resource_id == "decision"


def test_wrong_owner_revision_is_not_resolved_by_global_id() -> None:
    main = DecisionRecord(id="decision", name="Decision", latest_revision_id="shared-revision")
    other = DecisionRecord(id="other", name="Other")
    records = (
        project_record(),
        item("decisions", "decision", main),
        item(
            "drafts",
            "decision",
            DecisionDraft(decision_id="decision", editor_source="{", updated_at=STAMP),
        ),
        item("decisions", "other", other),
        item(
            "drafts",
            "other",
            DecisionDraft(decision_id="other", editor_source="{", updated_at=STAMP),
        ),
        item(
            "revisions",
            "shared-revision",
            DecisionRevision(
                id="shared-revision",
                decision_id="other",
                definition=definition(),
                content_hash=definition_hash(definition()),
                created_at=STAMP,
            ),
            ("other",),
        ),
    )

    with pytest.raises(ServiceFailure) as wrong_owner:
        validate_project_references(records)

    assert wrong_owner.value.error.reason == "project_reference_wrong_owner"
    assert wrong_owner.value.error.resource_id == "decision"


def test_noncanonical_current_label_key_fails_before_missing_parent_edges() -> None:
    records = (
        project_record(),
        *decision_records(),
        item("datasets", "dataset", DatasetRecord(id="dataset", name="Data", created_at=STAMP)),
        item(
            "cases",
            "case",
            CaseRecord(
                id="case",
                dataset_id="dataset",
                input_kind="json",
                input_source='{"text":"hello"}',
            ),
            ("dataset",),
        ),
        item(
            "labels",
            "wrong-label-id",
            LabelRecord(
                id="wrong-label-id",
                decision_id="decision",
                dataset_id="dataset",
                case_id="case",
                question_id="q",
                input_hash="0" * 64,
                acceptable_option_ids=("yes",),
                provenance="human",
                updated_at=STAMP,
            ),
            ("decision", "dataset"),
        ),
    )

    with pytest.raises(ServiceFailure) as invalid_label:
        validate_project_references(records)

    assert invalid_label.value.error.reason == "label_identity_mismatch"


def test_orphan_snapshot_is_rejected_as_a_hard_edge_before_hash_admission() -> None:
    snapshot = DatasetSnapshot(
        id="snapshot",
        dataset_id="missing-dataset",
        cases=(),
        content_hash="0" * 64,
        created_at=STAMP,
    )
    records = (project_record(), item("dataset_snapshots", "snapshot", snapshot))

    with pytest.raises(ServiceFailure) as missing_dataset:
        validate_project_references(records)

    assert missing_dataset.value.error.reason == "project_reference_missing"
    assert missing_dataset.value.error.resource_id == "snapshot"


def test_label_history_survives_current_case_removal() -> None:
    history = LabelChange(
        id="change-clear",
        operation_id="clear-case",
        decision_id="decision",
        dataset_id="dataset",
        case_id="removed-case",
        question_id="q",
        action="clear",
        label=None,
        created_at=STAMP,
    )
    records = (
        project_record(),
        *decision_records(),
        item("datasets", "dataset", DatasetRecord(id="dataset", name="Data", created_at=STAMP)),
        item("label_history", history.id, history, ("decision", "dataset")),
    )

    assert validate_project_references(records).warnings == ()


def test_readded_case_does_not_rebind_old_label_history_input() -> None:
    old_label = LabelRecord(
        id=label_id("removed-case", "q"),
        decision_id="decision",
        dataset_id="dataset",
        case_id="removed-case",
        question_id="q",
        input_hash=JsonDocument('{"value":"old input"}').content_hash,
        acceptable_option_ids=("yes",),
        provenance="human",
        updated_at=STAMP,
    )
    history = LabelChange(
        id="change-set",
        operation_id="set-before-removal",
        decision_id="decision",
        dataset_id="dataset",
        case_id=old_label.case_id,
        question_id=old_label.question_id,
        action="set",
        label=old_label,
        created_at=STAMP,
    )
    current_case = CaseRecord(
        id="removed-case",
        dataset_id="dataset",
        input_kind="json",
        input_source='{"value":"new input"}',
    )
    records = (
        project_record(),
        *decision_records(),
        item("datasets", "dataset", DatasetRecord(id="dataset", name="Data", created_at=STAMP)),
        item("cases", current_case.id, current_case, ("dataset",)),
        item("label_history", history.id, history, ("decision", "dataset")),
    )

    assert validate_project_references(records).warnings == ()


def _legacy_regression(
    *, question_id: str = "q", input_hash: str | None = None, content_hash: str | None = None
) -> RegressionRecord:
    record_hash = None if content_hash == "computed" else content_hash
    value = RegressionRecord(
        id="legacy-regression",
        content_hash=record_hash,
        decision_revision_id="revision",
        dataset_id="dataset",
        case_id="removed-case",
        question_id=question_id,
        input_source='{"value":"removed"}',
        input_hash=input_hash or JsonDocument('{"value":"removed"}').content_hash,
        acceptable_option_ids=("yes",),
        reason="Retained original expectation",
        created_at=STAMP,
    )
    if content_hash == "computed":
        return value.model_copy(update={"content_hash": regression_hash(value)})
    return value


def _legacy_regression_project(record: RegressionRecord) -> tuple[StoredRecord, ...]:
    revision = DecisionRevision(
        id="revision",
        decision_id="decision",
        definition=definition(),
        content_hash=definition_hash(definition()),
        created_at=STAMP,
    )
    return (
        project_record(),
        *decision_records(),
        item(
            "datasets", "dataset", DatasetRecord(id="dataset", name="Data", created_at=STAMP)
        ),
        item("revisions", "revision", revision, ("decision",)),
        item("regressions", record.id, record),
    )


def test_legacy_regression_warns_only_after_original_hashes_and_question_bind() -> None:
    valid = _legacy_regression(content_hash="computed")
    result = validate_project_references(_legacy_regression_project(valid))
    assert [warning.reason for warning in result.warnings] == [
        "legacy_regression_not_executable"
    ]

    for invalid in (
        _legacy_regression(input_hash="0" * 64),
        _legacy_regression(question_id="unknown-question"),
        _legacy_regression(content_hash="0" * 64),
    ):
        with pytest.raises(ServiceFailure) as rejected:
            validate_project_references(_legacy_regression_project(invalid))
        assert rejected.value.error.reason == "regression_evidence_mismatch"
