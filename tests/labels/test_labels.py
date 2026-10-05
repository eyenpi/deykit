from dataclasses import FrozenInstanceError, replace

import pytest
from pydantic import ValidationError

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelEdit, LabelService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import JsonDocument
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft, DecisionRecord, LabelChange, LabelSnapshot


def add(project, case_id="case", source='{"text":"hello","unselected":1}'):
    _, datasets, _, _ = project
    return datasets.add_case(
        "data",
        CaseInput(input_kind="json", input_source=source),
        case_id=case_id,
        expected_dataset_etag=datasets.read("data").etag,
        operation_id="add-" + case_id,
    )


def service(project):
    source, datasets, _, _ = project
    return LabelService(source, datasets.clock, datasets.id_factory)


def review(labels, case="case", decision="decision", **kwargs):
    return labels.read(decision, "data", case, **kwargs).review


def draft_edit(source, transform, operation="draft-change"):
    stored = source.read(ResourceKey("drafts", "decision"))
    draft = load_record(DecisionDraft, stored.body)
    text = transform(draft.editor_source)
    changed = DecisionDraft(decision_id="decision", editor_source=text, updated_at=draft.updated_at)
    source.commit(operation, (SourceChange(stored.key, dump_record(changed), stored.etag),))


def test_a12_labels_scoped_to_decisions_and_staged_choices_do_not_write(project):
    add(project)
    source, datasets, _, _ = project
    source.commit(
        "second",
        (
            SourceChange(
                ResourceKey("decisions", "other"),
                dump_record(DecisionRecord(id="other", name="Other")),
                None,
            ),
            SourceChange(
                ResourceKey("drafts", "other"),
                dump_record(
                    DecisionDraft(
                        decision_id="other",
                        editor_source=load_record(
                            DecisionDraft, source.read(ResourceKey("drafts", "decision")).body
                        ).editor_source,
                        updated_at=datasets.clock.utc_now(),
                    )
                ),
                None,
            ),
        ),
    )
    labels = service(project)
    original_dataset = datasets.read("data")
    staged = LabelEdit(review(labels), "set", ("A", "B"), "human")
    assert labels.read("decision", "data", "case").status == "unlabelled"
    labels.batch((staged,), operation_id="save")
    labels.set(
        review(labels, decision="other"),
        ("B",),
        provenance="authored_fixture",
        operation_id="save-other",
    )
    first = labels.read("decision", "data", "case")
    second = labels.read("other", "data", "case")
    assert first.label.acceptable_option_ids == ("A", "B")
    assert second.label.acceptable_option_ids == ("B",)
    assert first.label.id == second.label.id
    assert first.review.decision_id != second.review.decision_id
    assert datasets.read("data") == original_dataset
    with pytest.raises(FrozenInstanceError):
        first.review.input_hash = "other"
    with pytest.raises(ValidationError):
        first.label.note = "changed"


def test_a13_acceptable_dispute_clear_resolve_explicit_history(project):
    add(project)
    labels = service(project)
    labels.set(review(labels), ("B", "A"), provenance="imported_unknown", operation_id="set")
    view = labels.read("decision", "data", "case")
    assert not view.reasons and "B" in view.label.acceptable_option_ids
    labels.dispute(view.review, reason="Needs review", operation_id="dispute")
    view = labels.read("decision", "data", "case")
    assert view.reasons == ("disputed",)
    assert view.label.provenance == "imported_unknown"
    labels.set(view.review, ("B",), operation_id="edit-disputed")
    view = labels.read("decision", "data", "case")
    assert view.reasons == ("disputed",)  # Editing does not silently resolve.
    labels.clear(view.review, operation_id="clear")
    assert labels.read("decision", "data", "case").status == "unlabelled"
    labels.resolve(review(labels), ("B",), provenance="human", operation_id="resolve")
    view = labels.read("decision", "data", "case")
    assert view.label.acceptable_option_ids == ("B",) and not view.reasons
    history = {r.operation_id: r for r in labels.history("decision", "data", "case")}
    assert history["dispute"].action == "dispute"
    assert history["clear"].label is None
    assert history["resolve"].action == "resolve"
    assert history["set"].label.acceptable_option_ids == ("A", "B")


def test_a14_full_input_stales_tags_and_splits_do_not(project):
    added = add(project)
    _, datasets, _, _ = project
    labels = service(project)
    labels.set(review(labels), ("A",), provenance="model_generated", operation_id="set")
    edited = datasets.edit_case(
        "data",
        "case",
        CaseInput(
            input_kind="json",
            input_source=added.case.record.input_source,
            tags=("tag",),
            split="test",
        ),
        expected_dataset_etag=added.dataset.etag,
        expected_case_etag=added.case.etag,
        operation_id="metadata",
    )
    assert labels.read("decision", "data", "case").reasons == ()
    reviewed = review(labels)
    datasets.edit_case(
        "data",
        "case",
        CaseInput(input_kind="json", input_source='{"text":"hello","unselected":2}'),
        expected_dataset_etag=edited.dataset.etag,
        expected_case_etag=edited.case.etag,
        operation_id="input",
    )
    assert labels.read("decision", "data", "case").reasons == ("stale",)
    with pytest.raises(ServiceFailure):
        labels.set(reviewed, ("B",), operation_id="unseen-input")
    labels.set(review(labels), ("B",), operation_id="reviewed-input")
    assert labels.read("decision", "data", "case").label.provenance == "model_generated"


def test_combined_causes_and_deleted_ids_remain_inspectable(project):
    add(project)
    source, datasets, _, _ = project
    labels = service(project)
    labels.set(review(labels), ("A", "B"), provenance="human", operation_id="set")
    labels.dispute(review(labels), reason="ambiguous", operation_id="dispute")
    old = review(labels)
    draft_edit(source, lambda text: text.replace('"id":"A"', '"id":"C"'))
    case = datasets.case("data", "case")
    datasets.edit_case(
        "data",
        "case",
        CaseInput(input_kind="json", input_source='{"text":"new"}'),
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=case.etag,
        operation_id="edit",
    )
    view = labels.read("decision", "data", "case")
    assert view.reasons == ("disputed", "stale", "incompatible")
    assert view.missing_option_ids == ("A",)
    assert view.label.acceptable_option_ids == ("A", "B")
    for status in view.reasons:
        assert labels.list("decision", "data", status=status).total == 1
    with pytest.raises(ServiceFailure):
        labels.resolve(old, ("B",), operation_id="old-context")
    labels.resolve(view.review, ("B",), operation_id="resolve")
    assert labels.read("decision", "data", "case").reasons == ()


def test_question_replacement_keeps_old_label_listed_and_clearable(project):
    add(project)
    source, _, _, _ = project
    labels = service(project)
    labels.set(review(labels), ("A",), provenance="human", operation_id="set")
    draft_edit(source, lambda text: text.replace('"id":"category"', '"id":"new_question"'))
    assert labels.list("decision", "data").total == 2
    old = labels.list("decision", "data", status="incompatible").items[0]
    assert old.review.question_id == "category" and old.missing_option_ids == ("A",)
    labels.clear(old.review, operation_id="clear-old-question")
    assert labels.list("decision", "data").total == 1


def test_name_change_retains_option_identity_but_rejects_unreviewed_context(project):
    add(project)
    source, _, _, _ = project
    labels = service(project)
    labels.set(review(labels), ("A",), provenance="human", operation_id="set")
    before = labels.read("decision", "data", "case")
    draft_edit(source, lambda text: text.replace("Alpha", "Renamed"))
    after = labels.read("decision", "data", "case")
    assert not after.reasons and after.label.id == before.label.id
    with pytest.raises(ServiceFailure):
        labels.set(before.review, ("B",), operation_id="unseen-options")


def test_batch_validates_all_or_writes_none_and_provenance_required_for_new(project):
    add(project, "a")
    add(project, "b")
    source, _, _, _ = project
    labels = service(project)
    before = source.list_ids("label_history", ("decision", "data"))
    with pytest.raises(ServiceFailure):
        labels.batch(
            (
                LabelEdit(review(labels, "a"), "set", ("A",), "human"),
                LabelEdit(review(labels, "b"), "set", (), "human"),
            ),
            operation_id="bad",
        )
    assert labels.list("decision", "data", status="unlabelled").total == 2
    assert before == source.list_ids("label_history", ("decision", "data"))
    with pytest.raises(ServiceFailure):
        labels.set(review(labels, "a"), ("A",), operation_id="unspecified-provenance")
    with pytest.raises(ServiceFailure):
        labels.batch(
            (LabelEdit(review(labels, "a"), "set", ("A",), "human"),) * 2,
            operation_id="duplicate-target",
        )
    labels.batch(
        tuple(LabelEdit(review(labels, c), "set", ("A",), "authored_fixture") for c in ("a", "b")),
        operation_id="good",
    )
    assert labels.list("decision", "data", status="applicable").total == 2


def test_replay_original_before_current_validation_and_changed_intent_conflicts(project):
    add(project)
    labels = service(project)
    old = review(labels)
    first = labels.set(old, ("A",), provenance="human", operation_id="same")
    labels.set(review(labels), ("B",), operation_id="newer")
    replay = labels.set(old, ("A",), provenance="human", operation_id="same")
    assert replay.replayed and replay.changes == first.changes
    assert labels.read("decision", "data", "case").label.acceptable_option_ids == ("B",)
    with pytest.raises(ServiceFailure):
        labels.set(old, ("B",), provenance="human", operation_id="same")


def test_clear_absent_records_history_and_case_remove_readd_is_unlabelled(project):
    add(project)
    _, datasets, _, _ = project
    labels = service(project)
    cleared = labels.clear(review(labels), operation_id="clear-absent")
    assert cleared.changes[0].label is None
    labels.set(review(labels), ("A",), provenance="human", operation_id="set")
    case = datasets.case("data", "case")
    datasets.remove_case(
        "data",
        "case",
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=case.etag,
        operation_id="remove",
    )
    datasets.add_case(
        "data",
        CaseInput(input_kind="json", input_source=case.record.input_source),
        case_id="case",
        expected_dataset_etag=datasets.read("data").etag,
        operation_id="readd",
    )
    assert labels.read("decision", "data", "case").status == "unlabelled"
    assert len(labels.history("decision", "data", "case")) == 3


def test_saved_label_snapshot_unaffected_and_precise_input_semantics(project):
    add(project, source='{"text":"hello","n":9007199254740993.000000000000001}')
    source, datasets, _, _ = project
    labels = service(project)
    labels.set(review(labels), ("A",), provenance="human", operation_id="set")
    label = labels.read("decision", "data", "case").label
    snapshot = LabelSnapshot(
        id="frozen",
        decision_id="decision",
        dataset_snapshot_id="dataset",
        labels=(label,),
        content_hash=JsonDocument('{"frozen":true}').content_hash,
        created_at=datasets.clock.utc_now(),
    )
    source.commit(
        "freeze",
        (SourceChange(ResourceKey("label_snapshots", "frozen"), dump_record(snapshot), None),),
    )
    before = source.read(ResourceKey("label_snapshots", "frozen"))
    labels.resolve(review(labels), ("B",), operation_id="resolve")
    assert source.read(ResourceKey("label_snapshots", "frozen")) == before
    assert load_record(LabelSnapshot, before.body).labels[0].acceptable_option_ids == ("A",)
    assert (
        label.input_hash
        == JsonDocument('{"n":9007199254740993.0000000000000010,"text":"hello"}').content_hash
    )


@pytest.mark.parametrize("action,status", [("dispute", "active"), ("resolve", "disputed")])
def test_change_contract_rejects_false_transitions(project, action, status):
    add(project)
    labels = service(project)
    change = labels.set(review(labels), ("A",), provenance="human", operation_id="set").changes[0]
    with pytest.raises(ValidationError):
        LabelChange.model_validate(
            {
                **change.model_dump(),
                "action": action,
                "label": {**change.label.model_dump(), "status": status},
            }
        )


def test_forged_review_conflicts_without_writes(project):
    add(project)
    labels = service(project)
    with pytest.raises(ServiceFailure):
        labels.set(
            replace(review(labels), input_hash="0" * 64),
            ("A",),
            provenance="human",
            operation_id="forged",
        )
    assert labels.list("decision", "data", status="unlabelled").total == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"note": 123},
        {"acceptable_option_ids": None},
        {"acceptable_option_ids": ({"a": 1},)},
        {"provenance": {"secret": "never-print"}},
        {"action": {"secret": "never-print"}},
    ],
)
def test_malformed_label_edits_return_safe_failures(project, fields):
    add(project)
    labels = service(project)
    edit = replace(LabelEdit(review(labels), "set", ("A",), "human"), **fields)
    with pytest.raises(ServiceFailure) as failure:
        labels.batch((edit,), operation_id="malformed")
    assert failure.value.error.code == "validation_error"
    assert "never-print" not in str(failure.value)
