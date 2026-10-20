"""Mutable packed cases preserve exact values, edits, deletion and crash recovery."""

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord
from deykit.storage import FileProjectSource


def case(index, text='{"n":9007199254740993,"d":0.1234567890123456789,"s":"é"}'):
    key = ResourceKey("cases", f"case-{index}", ("data",))
    return key, dump_record(
        CaseRecord(id=key.resource_id, dataset_id="data", input_kind="json", input_source=text)
    )


def imported(source):
    return source.commit(
        "import", tuple(SourceChange(*case(i), None) for i in range(16)), intent_hash="a" * 64
    )


def test_large_import_keeps_cases_in_compact_storage(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        receipt = imported(source)
        assert not list((source.root / "source/cases").rglob("*.json"))
        key, changed = case(3, '{"edited":true}')
        saved = source.read(key)
        source.commit("edit", (SourceChange(key, changed, saved.etag),))
        assert source.read(key).body == changed
        source.commit("delete", (SourceChange(key, None, source.read(key).etag),))
        assert source.read(key) is None
        source.commit("recreate", (SourceChange(key, changed, None),))
        assert source.read(key).body == changed
        assert source.operation_receipt("import", intent_hash="a" * 64).changes == receipt.changes
        assert source.operation_history(key)[0].after.body == case(3)[1]
        assert len(source.operation_history(key)) == 4
        assert not list((source.root / "source/cases").rglob("*.json"))
    with FileProjectSource(tmp_path / "project") as reader:
        assert len(reader.read_records()) == 16
        assert reader.read(case(0)[0]).body == case(0)[1]


@pytest.mark.parametrize("point", ["prepared", "decided", "applied:0", "chunk_linked", "archived"])
def test_packed_edit_recovers_without_changing_other_cases(tmp_path, point):
    root = tmp_path / "project"
    key, changed = case(3, '{"edited":true}')
    with FileProjectSource(root, create=True) as source:
        imported(source)
        saved = source.read(key)

        def crash(stage):
            if stage == point:
                raise OSError("authored interruption")

        source._hook = crash
        with pytest.raises(ServiceFailure):
            source.commit("edit", (SourceChange(key, changed, saved.etag),))
    with FileProjectSource(root) as reader:
        assert reader.read(key).body == (saved.body if point == "prepared" else changed)
        assert reader.read(case(0)[0]).body == case(0)[1]


def test_legacy_cases_remain_readable_beside_packed_cases(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        key, body = case(99)
        source.commit("legacy", (SourceChange(key, body, None),))
        assert (source.root / "source/cases/data/case-99.json").read_bytes() == body
        imported(source)
        assert len(source.read_records()) == 17
        assert source.read(key).body == body


def test_packed_case_edits_in_one_epoch_keep_compact_layout(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        with source.consistent_read():
            imported(source)
            key, body = case(3, '{"nested":true}')
            source.commit("edit", (SourceChange(key, body, source.read(key).etag),))
            assert source.read(key).body == body
        assert not list((source.root / "source/cases").rglob("*.json"))


@pytest.mark.parametrize("point", ["applied:0", "chunk_linked"])
def test_conversion_of_legacy_cases_recovers_after_physical_removal(tmp_path, point):
    root = tmp_path / "project"
    with FileProjectSource(root, create=True) as source:
        for i in range(16):
            source.commit(f"old-{i}", (SourceChange(*case(i), None),))
        edits = tuple(
            SourceChange(*case(i, '{"converted":true}'), source.read(case(i)[0]).etag)
            for i in range(16)
        )

        def crash(stage):
            if stage == point:
                raise OSError("authored interruption")

        source._hook = crash
        with pytest.raises(ServiceFailure):
            source.commit("convert", edits)
    with FileProjectSource(root) as source:
        assert {r.key: r.body for r in source.read_records()} == {c.key: c.body for c in edits}
    assert not list((root / "source/cases").rglob("*.json"))


def test_physical_case_cannot_shadow_a_packed_case_or_tombstone(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        imported(source)
        key, body = case(3)
        source.commit("delete", (SourceChange(key, None, source.read(key).etag),))
        source.files.replace(("source", "cases", "data", "case-3.json"), body)
        with pytest.raises(ServiceFailure):
            source.read_records()


def test_incremental_views_bind_changes_to_exact_previous_records(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        with source.consistent_read():
            before = source.read_records()
            imported(source)
            created = source.read_record_view(before)
            assert created.previous_records is before
            assert len(created.changes) == 16 and created.deleted_keys == ()
            key, body = case(3, '{"changed":true}')
            source.commit("edit", (SourceChange(key, body, source.read(key).etag),))
            edited = source.read_record_view(created.records)
            assert len(edited.changes) == 1 and edited.changes[0].body == body
            source.commit("delete", (SourceChange(key, None, source.read(key).etag),))
            deleted = source.read_record_view(edited.records)
            assert deleted.changes == () and deleted.deleted_keys == (key,)
        walks = []
        original = source.files.read_tree

        def observe(parts, *args, **kwargs):
            walks.append(parts)
            return original(parts, *args, **kwargs)

        monkeypatch.setattr(source.files, "read_tree", observe)
        unchanged = source.read_record_view(deleted.records)
        assert unchanged.changes == ()
        assert ("source",) in walks and ("history", "operations") in walks


def test_projection_budget_uses_full_capture_without_losing_case_edits(tmp_path, monkeypatch):
    from deykit.storage import _source_view

    monkeypatch.setattr(_source_view, "_MAX_OPERATIONS", 1)
    with FileProjectSource(tmp_path / "project", create=True) as source:
        imported(source)
        key, body = case(3, '{"budget":true}')
        source.commit("edit", (SourceChange(key, body, source.read(key).etag),))
        assert len(source.read_records()) == 16 and source.read(key).body == body
        assert source._source_view.view is None
