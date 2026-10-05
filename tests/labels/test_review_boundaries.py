"""Externally edited identities and malformed raw DTOs must fail before mutation/replay."""

from dataclasses import replace

import pytest

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelEdit, LabelReview, LabelService
from deykit.application.splits import SplitPreview, SplitService
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import LabelRecord
from deykit.domain.label_identity import label_id


def services(project):
    source, datasets, _, _ = project
    for key in ("a", "b"):
        datasets.add_case(
            "data",
            CaseInput(input_kind="json", input_source='{"text":"same"}'),
            case_id=key,
            expected_dataset_etag=datasets.read("data").etag,
            operation_id="add-" + key,
        )
    return (
        source,
        LabelService(source, datasets.clock, datasets.id_factory),
        SplitService(source, datasets.clock, datasets.id_factory),
    )


def portable_bytes(source):
    return {
        str(p.relative_to(source.root)): p.read_bytes()
        for p in source.root.rglob("*")
        if p.is_file() and ".deykit" not in p.relative_to(source.root).parts
    }


def test_same_input_other_case_cannot_substitute_label_identity(project):
    source, labels, _ = services(project)
    view = labels.read("decision", "data", "a")
    label = labels.set(view.review, ("A",), provenance="human", operation_id="set").changes[0].label
    key = ResourceKey("labels", label.id, ("decision", "data"))
    stored = source.read(key)
    # Valid persisted envelope, but inconsistent with the deterministic case/question key.
    foreign = LabelRecord.model_validate({**label.model_dump(), "case_id": "b"})
    source.commit("external-edit", (SourceChange(key, dump_record(foreign), stored.etag),))
    before = portable_bytes(source)
    for call in (
        lambda: labels.read("decision", "data", "a"),
        lambda: labels.list("decision", "data"),
        lambda: labels.set(view.review, ("B",), provenance="human", operation_id="save"),
    ):
        with pytest.raises(ServiceFailure) as error:
            call()
        assert error.value.error.reason == "label_identity_mismatch"
    assert portable_bytes(source) == before


def test_list_detects_miskeyed_record_instead_of_silently_hiding_it(project):
    source, labels, _ = services(project)
    view = labels.read("decision", "data", "a")
    label = labels.set(view.review, ("A",), provenance="human", operation_id="set").changes[0].label
    key = ResourceKey("labels", label.id, ("decision", "data"))
    stored = source.read(key)
    wrong = LabelRecord.model_validate({**label.model_dump(), "id": "wrong-label"})
    source.commit(
        "external-move",
        (
            SourceChange(key, None, stored.etag),
            SourceChange(ResourceKey("labels", "wrong-label", key.scope), dump_record(wrong), None),
        ),
    )
    assert labels.read("decision", "data", "a").label is None
    before = portable_bytes(source)
    with pytest.raises(ServiceFailure) as error:
        labels.list("decision", "data")
    assert error.value.error.reason == "label_identity_mismatch"
    assert portable_bytes(source) == before


def test_stored_question_identity_must_agree_with_deterministic_id(project):
    source, labels, _ = services(project)
    label = (
        labels.set(
            labels.read("decision", "data", "a").review,
            ("A",),
            provenance="human",
            operation_id="set",
        )
        .changes[0]
        .label
    )
    key = ResourceKey("labels", label_id("a", "category"), ("decision", "data"))
    changed = LabelRecord.model_validate({**label.model_dump(), "question_id": "elsewhere"})
    source.commit(
        "external-edit", (SourceChange(key, dump_record(changed), source.read(key).etag),)
    )
    with pytest.raises(ServiceFailure) as error:
        labels.read("decision", "data", "a")
    assert error.value.error.reason == "label_identity_mismatch"


def test_boolean_counts_never_enter_immutable_split_evidence_even_on_replay(project):
    source, datasets, _, dataset = project
    datasets.add_case(
        "data",
        CaseInput(input_kind="text", input_source='"one"'),
        case_id="a",
        expected_dataset_etag=dataset.etag,
        operation_id="add-a",
    )
    splits = SplitService(source, datasets.clock, datasets.id_factory)
    # True == 1 and False == 0 must never certify forged counts.
    preview = splits.preview("data", assignments=(("a", "test"),))
    forged = replace(
        preview, counts=(("development", False), ("calibration", False), ("test", True))
    )
    before = portable_bytes(source)
    with pytest.raises(ServiceFailure) as error:
        splits.commit(forged, operation_id="split")
    assert error.value.error.reason == "invalid_split_counts"
    assert portable_bytes(source) == before
    original = splits.commit(preview, operation_id="split")
    before = portable_bytes(source)
    with pytest.raises(ServiceFailure):
        splits.commit(forged, operation_id="split")
    assert portable_bytes(source) == before
    assert splits.commit(preview, operation_id="split").snapshot == original.snapshot


class NoSourceAccess:
    def __getattr__(self, name):
        raise AssertionError("Malformed request reached source: " + name)


def test_malformed_dataclasses_and_controls_fail_before_source_access(project):
    source, labels, splits = services(project)
    review = labels.read("decision", "data", "a").review
    preview = splits.preview("data")
    clock, ids = project[1].clock, project[1].id_factory
    blocked_labels = LabelService(NoSourceAccess(), clock, ids)
    blocked_splits = SplitService(NoSourceAccess(), clock, ids)
    edit = LabelEdit(review, "set", ("A",), "human")
    # A real valid operation exists. Malformed retries must not bypass admission via replay.
    labels.batch((edit,), operation_id="existing")
    splits.commit(preview, operation_id="existing-split")
    malformed_reviews = [None, object(), object.__new__(LabelReview)]
    for field in (
        "decision_id",
        "dataset_id",
        "case_id",
        "question_id",
        "input_hash",
        "decision_etag",
        "draft_etag",
        "label_etag",
    ):
        malformed_reviews.extend(
            replace(review, **{field: value}) for value in ([], {}, object(), "\ud800", "")
        )
    calls = [
        lambda r=r: blocked_labels.clear(r, operation_id="existing") for r in malformed_reviews
    ]
    malformed_edits = [
        None,
        object(),
        object.__new__(LabelEdit),
        replace(edit, action=[]),
        replace(edit, acceptable_option_ids=(["A"],)),
        replace(edit, acceptable_option_ids=["A"]),
        replace(edit, acceptable_option_ids=("",)),
        replace(edit, provenance=object()),
        replace(edit, note="\ud800"),
    ]
    calls += [
        lambda e=e: blocked_labels.batch((e,), operation_id="existing") for e in malformed_edits
    ]
    calls += [
        lambda: blocked_labels.batch(None, operation_id="existing"),
        lambda: blocked_labels.batch([edit], operation_id="existing"),
        lambda: blocked_labels.list("decision", "data", status=[]),
        lambda: blocked_labels.list("decision", "data", cursor=object()),
        lambda: blocked_labels.list("decision", "data", limit=True),
        lambda: blocked_labels.list("decision", "data", limit=0),
        lambda: blocked_labels.read("decision", "data", "a", question_id=""),
        lambda: blocked_labels.read("decision", "data", "a", question_id=[]),
        lambda: blocked_labels.history("decision", "data", "a", question_id=""),
        lambda: blocked_labels.history([], "data", "a"),
        lambda: blocked_labels.set(review, ("A",), provenance="human", operation_id="\ud800"),
        lambda: blocked_splits.preview("data", seed=True),
        lambda: blocked_splits.preview("data", ratios_source=object()),
        lambda: blocked_splits.preview("data", ratios_source='{"test":true}'),
        lambda: blocked_splits.preview("data", assignments=(("a", object()),)),
        lambda: blocked_splits.preview([], assignments=()),
        lambda: blocked_splits.preview("data", assignments=(["a", "test"],)),
    ]
    malformed_previews = [None, object(), object.__new__(SplitPreview)]
    fields = {
        "dataset_id": [[], object(), "\ud800", ""],
        "dataset_etag": [None, True, "not-hash"],
        "input_identity": [False, ""],
        "algorithm": [[], object(), "arbitrary"],
        "seed": [True, "1", object()],
        "ratios_source": [[], "\ud800", '{"test":true}'],
        "assignments": [None, [("a", "test")], (("a", []),), ((object(), "test"),)],
        "groups": [None, ["a"], ((object(),),), ((),), (("\ud800",),)],
        "counts": [None, (("test", True),), (("test", object()),), (([], 1),)],
    }
    for name, values in fields.items():
        malformed_previews.extend(replace(preview, **{name: value}) for value in values)
    calls += [
        lambda p=p: blocked_splits.commit(p, operation_id="existing-split")
        for p in malformed_previews
    ]
    before = portable_bytes(source)
    for call in calls:
        with pytest.raises(ServiceFailure) as error:
            call()
        assert error.value.error.code == "validation_error"
        assert "object at" not in str(error.value)
    assert portable_bytes(source) == before
