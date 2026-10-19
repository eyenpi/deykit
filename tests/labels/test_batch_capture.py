"""Label snapshots bound read work without losing external-edit detection."""

import pytest

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.application.labels import LabelEdit, LabelService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import CaseRecord, DatasetRecord, DecisionDraft, DecisionRecord


class CountedSource:
    def __init__(self, source):
        self.source = source
        self.reads = 0
        self.captures = 0

    def __getattr__(self, name):
        return getattr(self.source, name)

    def read(self, key):
        self.reads += 1
        return self.source.read(key)

    def capture_snapshot(self):
        self.captures += 1
        return self.source.capture_snapshot()


def setup(project):
    source, datasets, _, _ = project
    for case_id in ("a", "b"):
        datasets.add_case(
            "data",
            CaseInput(input_kind="json", input_source='{"text":"example"}'),
            case_id=case_id,
            expected_dataset_etag=datasets.read("data").etag,
            operation_id="add-" + case_id,
        )
    counted = CountedSource(source)
    labels = LabelService(counted, datasets.clock, datasets.id_factory)
    edits = tuple(
        LabelEdit(labels.read("decision", "data", case_id).review, "set", ("A",), "model_generated")
        for case_id in ("a", "b")
    )
    counted.reads = counted.captures = 0
    return source, datasets, counted, labels, edits


def test_label_read_and_batch_use_fresh_bounded_snapshots(project):
    _, _, counted, labels, edits = setup(project)
    labels.read("decision", "data", "a")
    assert counted.captures == 1
    assert counted.reads == 0
    counted.captures = 0
    result = labels.batch(edits, operation_id="batch")
    assert [change.label.acceptable_option_ids for change in result.changes] == [("A",), ("A",)]
    assert counted.captures == 2
    assert counted.reads == 0
    captures = counted.captures
    replay = labels.batch(edits, operation_id="batch")
    assert replay.replayed and replay.changes == result.changes
    assert counted.captures == captures


@pytest.mark.parametrize("target", ["input", "draft", "decision", "dataset", "history"])
def test_batch_rechecks_external_edits_after_preparation(project, target):
    source, datasets, _, _, edits = setup(project)
    fired = False

    def ids():
        nonlocal fired
        if not fired:
            fired = True
            if target == "input":
                key, kind = ResourceKey("cases", "a", ("data",)), CaseRecord
            elif target == "draft":
                key, kind = ResourceKey("drafts", "decision"), DecisionDraft
            elif target == "decision":
                key, kind = ResourceKey("decisions", "decision"), DecisionRecord
            elif target == "dataset":
                key, kind = ResourceKey("datasets", "data"), DatasetRecord
            else:
                blob = next((source.root / "history/operations").glob("*/new-0.json"))
                blob.write_bytes(b"corrupted history")
                return datasets.id_factory()
            stored = source.read(key)
            record = load_record(kind, stored.body)
            updates = (
                {"input_source": '{"text":"edited"}'}
                if target == "input"
                else (
                    {"editor_source": record.editor_source.replace("Alpha", "Changed")}
                    if target == "draft"
                    else {"archived": True}
                )
            )
            from deykit.storage.records import key_path

            source.files.replace(key_path(key), dump_record(record.model_copy(update=updates)))
        return datasets.id_factory()

    labels = LabelService(source, datasets.clock, ids)
    with pytest.raises(ServiceFailure):
        labels.batch(edits, operation_id="raced-batch")
    assert not (source.root / "history/operations/raced-batch").exists()
    assert not (source.root / "source/labels/decision/data").exists()


def test_duplicate_snapshot_keys_are_rejected_on_read(project):
    source, datasets, _, _, _ = setup(project)
    records = source.capture_snapshot()
    labels = LabelService(source, datasets.clock, capture_snapshot=lambda: records + (records[0],))
    with pytest.raises(ServiceFailure) as failure:
        labels.read("decision", "data", "a")
    assert failure.value.error.reason == "duplicate_captured_key"
