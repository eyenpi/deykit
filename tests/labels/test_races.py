"""Real filesystem source races and recoverable all-or-nothing batch evidence."""

from contextlib import contextmanager

import pytest

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelEdit, LabelService
from deykit.application.splits import SplitService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft
from deykit.storage import FileProjectSource


class InterleavedSource:
    def __init__(self, source, interleave):
        self.source, self.interleave = source, interleave

    def __getattr__(self, name):
        return getattr(self.source, name)

    @contextmanager
    def consistent_read(self):
        if self.interleave is not None:
            run, self.interleave = self.interleave, None
            run()
        with self.source.consistent_read():
            yield self


def setup(project):
    source, datasets, _, _ = project
    for case in ("a", "b"):
        datasets.add_case(
            "data",
            CaseInput(input_kind="json", input_source='{"text":"hello"}'),
            case_id=case,
            expected_dataset_etag=datasets.read("data").etag,
            operation_id="add-" + case,
        )
    return source, datasets, LabelService(source, datasets.clock, datasets.id_factory)


def request(labels, case="a"):
    return labels.read("decision", "data", case).review


@pytest.mark.parametrize("change", ["input", "draft", "label"])
def test_actual_source_change_before_save_boundary_conflicts(project, change):
    source, datasets, labels = setup(project)
    reviewed = request(labels)

    def interleave():
        if change == "input":
            item = datasets.case("data", "a")
            datasets.edit_case(
                "data",
                "a",
                CaseInput(input_kind="json", input_source='{"text":"changed"}'),
                expected_dataset_etag=datasets.read("data").etag,
                expected_case_etag=item.etag,
                operation_id="race-input",
            )
        elif change == "draft":
            stored = source.read(ResourceKey("drafts", "decision"))
            draft = load_record(DecisionDraft, stored.body)
            changed = DecisionDraft(
                decision_id="decision",
                updated_at=draft.updated_at,
                editor_source=draft.editor_source.replace("Alpha", "New"),
            )
            source.commit(
                "race-draft", (SourceChange(stored.key, dump_record(changed), stored.etag),)
            )
        else:
            labels.set(request(labels), ("B",), provenance="human", operation_id="race-label")

    raced = LabelService(InterleavedSource(source, interleave), datasets.clock, datasets.id_factory)
    with pytest.raises(ServiceFailure) as failure:
        raced.set(reviewed, ("A",), provenance="human", operation_id="race-save")
    assert failure.value.error.code == "conflict"
    history = labels.history("decision", "data", "a")
    assert all(record.operation_id != "race-save" for record in history)


def test_source_lock_spans_validation_generation_and_commit(project):
    source, datasets, labels = setup(project)
    reviewed = request(labels)
    competing = FileProjectSource(source.root)
    blocked = []

    def checked_id():
        # A second real adapter cannot mutate source while label preparation is in progress.
        try:
            with competing.consistent_read():
                raise AssertionError("Source lock was released during label save")
        except ServiceFailure as error:
            blocked.append(error.error.code)
        return datasets.id_factory()

    try:
        service = LabelService(source, datasets.clock, checked_id)
        service.set(reviewed, ("A",), provenance="human", operation_id="save")
    finally:
        competing.close()
    assert blocked == ["conflict"]
    assert labels.read("decision", "data", "a").label.acceptable_option_ids == ("A",)


def test_replay_lookup_is_inside_source_boundary_before_ids_or_validation(project):
    source, datasets, labels = setup(project)
    reviewed = request(labels)
    originals = []

    def interleave():
        originals.append(labels.set(reviewed, ("A",), provenance="human", operation_id="same"))
        labels.set(request(labels), ("B",), operation_id="newer")

    def forbidden():
        raise AssertionError("Generated an ID on replay")

    raced = LabelService(InterleavedSource(source, interleave), datasets.clock, forbidden)
    result = raced.set(reviewed, ("A",), provenance="human", operation_id="same")
    assert result.replayed and result.changes == originals[0].changes


def test_split_replay_lookup_is_inside_source_boundary(project):
    source, datasets, _ = setup(project)
    splits = SplitService(source, datasets.clock, datasets.id_factory)
    preview = splits.preview("data")
    original = []

    def interleave():
        original.append(splits.commit(preview, operation_id="same"))
        splits.commit(
            splits.preview("data", assignments=(("a", "test"), ("b", "test"))), operation_id="later"
        )

    def forbidden():
        raise AssertionError("Generated an ID on replay")

    raced = SplitService(InterleavedSource(source, interleave), datasets.clock, forbidden)
    result = raced.commit(preview, operation_id="same")
    assert result.replayed and result.snapshot == original[0].snapshot


@pytest.mark.parametrize("checkpoint", ["prepared", "decided", "applied:1"])
def test_batch_crash_recovery_never_exposes_partial_label_history(project, checkpoint):
    source, datasets, labels = setup(project)
    edits = tuple(LabelEdit(request(labels, case), "set", ("A",), "human") for case in ("a", "b"))

    class Crash(RuntimeError):
        pass

    triggered = []

    def crash(phase):
        if phase == checkpoint and not triggered:
            triggered.append(phase)
            raise Crash()

    crashing = FileProjectSource(source.root, fault_hook=crash)
    broken = LabelService(crashing, datasets.clock, datasets.id_factory)
    try:
        with pytest.raises(Crash):
            broken.batch(edits, operation_id="batch-crash")
    finally:
        crashing.close()
    count = labels.list("decision", "data", status="applicable").total
    histories = [labels.history("decision", "data", case) for case in ("a", "b")]
    assert count in (0, 2)
    assert [len(items) for items in histories] == [count // 2, count // 2]
    replay = labels.batch(edits, operation_id="batch-crash")
    assert len(replay.changes) == 2
    assert labels.list("decision", "data", status="applicable").total == 2
