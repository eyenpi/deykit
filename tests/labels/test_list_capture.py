import pytest

from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DecisionDraft,
    LabelRecord,
)
from deykit.domain.label_identity import label_id
from deykit.storage import FileProjectSource


def add_case(project, case_id):
    _, datasets, _, _ = project
    return datasets.add_case(
        "data",
        CaseInput(input_kind="json", input_source='{"text":"hello"}'),
        case_id=case_id,
        expected_dataset_etag=datasets.read("data").etag,
        operation_id="add-" + case_id,
    )


def label_service(project):
    source, datasets, _, _ = project
    return LabelService(source, datasets.clock, datasets.id_factory)


class CountedSource:
    def __init__(self, source):
        self.source = source
        self.read_calls = 0
        self.list_calls = 0
        self.capture_calls = 0

    def __getattr__(self, name):
        return getattr(self.source, name)

    def read(self, key):
        self.read_calls += 1
        return self.source.read(key)

    def list_ids(self, collection, scope=()):
        self.list_calls += 1
        return self.source.list_ids(collection, scope)

    def capture_snapshot(self):
        self.capture_calls += 1
        return self.source.capture_snapshot()


def change_definition(source, transform, operation_id):
    stored = source.read(ResourceKey("drafts", "decision"))
    draft = load_record(DecisionDraft, stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    changed = DecisionDraft(
        decision_id=draft.decision_id,
        editor_source=dump_record(transform(definition)).decode(),
        updated_at=draft.updated_at,
    )
    source.commit(operation_id, (SourceChange(stored.key, dump_record(changed), stored.etag),))


def test_capture_list_matches_legacy_on_nine_real_cases_and_label_history(project):
    source, datasets, _, _ = project
    for index in range(9):
        add_case(project, f"case-{index}")
    legacy = label_service(project)
    legacy.set(
        legacy.read("decision", "data", "case-0").review,
        ("A",),
        provenance="human",
        operation_id="label-case-0",
    )
    legacy.set(
        legacy.read("decision", "data", "case-1").review,
        ("B",),
        provenance="human",
        operation_id="label-case-1",
    )
    legacy.dispute(
        legacy.read("decision", "data", "case-1").review,
        reason="Review this label",
        operation_id="dispute-case-1",
    )
    legacy.set(
        legacy.read("decision", "data", "case-2").review,
        ("A",),
        provenance="human",
        operation_id="label-case-2",
    )
    case = datasets.case("data", "case-2")
    datasets.edit_case(
        "data",
        "case-2",
        CaseInput(input_kind="json", input_source='{"text":"changed"}'),
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=case.etag,
        operation_id="stale-case-2",
    )

    expected = legacy.list("decision", "data")
    counted = CountedSource(source)
    optimized = LabelService(
        counted,
        datasets.clock,
        datasets.id_factory,
        capture_snapshot=counted.capture_snapshot,
    )
    actual = optimized.list("decision", "data")

    assert actual == expected
    assert actual.total == 9
    assert counted.capture_calls == 1
    assert counted.read_calls == 0
    assert counted.list_calls == 0
    assert len(legacy.history("decision", "data", "case-1")) == 2
    for status in ("unlabelled", "disputed", "stale", "applicable"):
        assert optimized.list("decision", "data", status=status) == legacy.list(
            "decision", "data", status=status
        )
    assert optimized.list("decision", "data", limit=3) == legacy.list("decision", "data", limit=3)
    cursor_item = expected.items[2]
    cursor_id = label_id(cursor_item.review.case_id, cursor_item.review.question_id)
    assert optimized.list("decision", "data", cursor=cursor_id, limit=2) == legacy.list(
        "decision", "data", cursor=cursor_id, limit=2
    )


def test_capture_retains_removed_question_labels_as_incompatible_and_clearable(project):
    source, datasets, _, _ = project
    add_case(project, "case")
    legacy = label_service(project)
    legacy.set(
        legacy.read("decision", "data", "case").review,
        ("A",),
        provenance="human",
        operation_id="old-question-label",
    )

    def replace_question(definition):
        return definition.model_copy(
            update={
                "questions": (
                    ChoiceQuestion(
                        id="new-question",
                        instructions="Choose the current option.",
                        options=(
                            ChoiceOption(id="A", name="Alpha"),
                            ChoiceOption(id="B", name="Beta"),
                        ),
                    ),
                )
            }
        )

    change_definition(source, replace_question, "replace-question")
    counted = CountedSource(source)
    captured = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=counted.capture_snapshot
    )
    result = captured.list("decision", "data", status="incompatible")
    old = next(item for item in result.items if item.review.question_id == "category")
    assert result.total == 1
    assert old.label is not None
    assert old.reasons
    captured.clear(old.review, operation_id="clear-removed-question")
    assert all(
        item.review.question_id != "category" for item in captured.list("decision", "data").items
    )


def test_capture_validation_and_missing_referenced_case_are_not_hidden(project):
    source, datasets, _, _ = project
    add_case(project, "case")
    labels = label_service(project)
    labels.set(
        labels.read("decision", "data", "case").review,
        ("A",),
        provenance="human",
        operation_id="label-case",
    )
    counted = CountedSource(source)
    original_capture = counted.capture_snapshot

    def wrong_label_identity():
        records = original_capture()
        updated = []
        for record in records:
            if record.key.collection == "labels":
                label = load_record(LabelRecord, record.body)
                wrong = label.model_copy(update={"dataset_id": "other-dataset"})
                record = StoredRecord(record.key, dump_record(wrong), record.etag)
            updated.append(record)
        return tuple(updated)

    captured = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=wrong_label_identity
    )
    with pytest.raises(ServiceFailure) as failure:
        captured.list("decision", "data")
    assert failure.value.error.reason == "label_identity_mismatch"

    def duplicate_key():
        records = original_capture()
        return records + (records[0],)

    captured = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=duplicate_key
    )
    with pytest.raises(ServiceFailure) as failure:
        captured.list("decision", "data")
    assert failure.value.error.reason == "duplicate_captured_key"

    def missing_case():
        return tuple(
            record
            for record in original_capture()
            if record.key != ResourceKey("cases", "case", ("data",))
        )

    captured = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=missing_case
    )
    with pytest.raises(ServiceFailure) as failure:
        captured.list("decision", "data")
    assert failure.value.error.code == "not_found"
    assert failure.value.error.resource_id == "case"


def test_capture_controls_are_admitted_before_any_source_access(project):
    source, datasets, _, _ = project
    counted = CountedSource(source)
    service = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=counted.capture_snapshot
    )
    for values in (
        {"status": "unknown"},
        {"limit": 0},
        {"cursor": "invalid cursor"},
    ):
        with pytest.raises(ServiceFailure):
            service.list("decision", "data", **values)
    assert counted.capture_calls == counted.read_calls == counted.list_calls == 0


def test_capture_supports_empty_and_unlabelled_projects(project):
    source, datasets, _, _ = project
    counted = CountedSource(source)
    service = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=counted.capture_snapshot
    )
    empty = service.list("decision", "data")
    assert empty.items == ()
    assert empty.total == 0
    assert counted.capture_calls == 1

    add_case(project, "case")
    unlabelled = service.list("decision", "data")
    assert unlabelled.total == 1
    assert unlabelled.items[0].label is None
    assert unlabelled.items[0].status == "unlabelled"
    assert counted.capture_calls == 2


def test_capture_invalid_draft_fails_before_constructing_a_partial_page(project):
    source, datasets, _, _ = project
    add_case(project, "case")
    counted = CountedSource(source)
    original_capture = counted.capture_snapshot

    def invalid_draft():
        records = original_capture()
        updated = []
        for record in records:
            if record.key == ResourceKey("drafts", "decision"):
                draft = load_record(DecisionDraft, record.body)
                malformed_definition = draft.model_copy(update={"editor_source": "not-json"})
                record = StoredRecord(record.key, dump_record(malformed_definition), record.etag)
            updated.append(record)
        return tuple(updated)

    service = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=invalid_draft
    )
    with pytest.raises(ServiceFailure) as failure:
        service.list("decision", "data")
    assert failure.value.error.reason == "invalid_decision_draft"
    assert counted.capture_calls == 1


def test_capture_propagates_unrelated_history_corruption_before_returning_a_page(project):
    source, datasets, _, _ = project
    add_case(project, "case")
    labels = label_service(project)
    labels.set(
        labels.read("decision", "data", "case").review,
        ("A",),
        provenance="human",
        operation_id="label-case",
    )
    history = next((source.root / "source" / "label_history").rglob("*.json"))
    history.write_bytes(b"not a record")
    counted = CountedSource(source)
    captured = LabelService(
        counted, datasets.clock, datasets.id_factory, capture_snapshot=counted.capture_snapshot
    )
    with pytest.raises(ServiceFailure) as failure:
        captured.list("decision", "data")
    assert failure.value.error.reason == "invalid_json"
    assert counted.capture_calls == 1
    assert counted.read_calls == counted.list_calls == 0


def test_capture_rejects_external_change_and_each_request_recaptures(project):
    source, datasets, _, _ = project
    add_case(project, "case")
    dataset_record = datasets.read("data").record

    def edit_during_capture(checkpoint):
        if checkpoint == "snapshot_captured":
            (source.root / "source" / "datasets" / "data.json").write_bytes(
                dump_record(dataset_record.model_copy(update={"name": "Changed outside"}))
            )

    unstable = FileProjectSource(source.root, fault_hook=edit_during_capture)
    try:
        service = LabelService(
            unstable,
            datasets.clock,
            datasets.id_factory,
            capture_snapshot=unstable.capture_snapshot,
        )
        with pytest.raises(ServiceFailure) as failure:
            service.list("decision", "data")
        assert failure.value.error.reason == "unstable_source"
    finally:
        unstable.close()

    # A subsequent request captures independently and observes a later commit.
    fresh_source = FileProjectSource(source.root)
    try:
        counter = CountedSource(fresh_source)
        fresh_datasets = DatasetService(fresh_source, datasets.clock, datasets.id_factory)
        service = LabelService(
            counter,
            fresh_datasets.clock,
            fresh_datasets.id_factory,
            capture_snapshot=counter.capture_snapshot,
        )
        assert service.list("decision", "data").total == 1
        fresh_datasets.add_case(
            "data",
            CaseInput(input_kind="json", input_source='{"text":"next"}'),
            case_id="case-2",
            expected_dataset_etag=fresh_datasets.read("data").etag,
            operation_id="add-case-2",
        )
        assert service.list("decision", "data").total == 2
        assert counter.capture_calls == 2
        assert counter.read_calls == counter.list_calls == 0
    finally:
        fresh_source.close()
