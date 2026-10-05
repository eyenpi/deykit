import os

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft
from deykit.storage import FileProjectSource


def body():
    return dump_record(
        DecisionDraft(decision_id="d", editor_source="safe", updated_at="2026-10-05T12:00:00Z")
    )


@pytest.mark.parametrize(
    "location",
    ["source", "source/drafts", "source/drafts/d.json", "history", ".deykit", ".deykit/locks"],
)
def test_symlinked_internal_paths_cannot_read_or_write_outside_project(tmp_path, location):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    target = root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    if location.endswith(".json"):
        victim = outside / "victim.json"
        victim.write_bytes(body())
        target.symlink_to(victim)
    else:
        target.symlink_to(outside, target_is_directory=True)
    before = tuple(outside.rglob("*"))
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure):
            source.commit("write", (SourceChange(ResourceKey("drafts", "d"), body(), None),))
    assert tuple(outside.rglob("*")) == before
    if location.endswith(".json"):
        assert victim.read_bytes() == body()


def test_hardlinked_source_is_rejected(tmp_path):
    root = tmp_path / "project"
    (root / "source/drafts").mkdir(parents=True)
    victim = tmp_path / "victim.json"
    victim.write_bytes(body())
    os.link(victim, root / "source/drafts/d.json")
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure) as error:
            source.read(ResourceKey("drafts", "d"))
        assert error.value.error.reason == "unsafe_source_path"
    assert victim.read_bytes() == body()


def test_scoped_case_ids_can_repeat_without_aliasing(tmp_path):
    from deykit.contracts.records import CaseRecord

    with FileProjectSource(tmp_path, create=True) as source:
        for dataset in ("a", "b"):
            case = CaseRecord(id="same", dataset_id=dataset, input_kind="text", input_source='"x"')
            source.commit(
                dataset,
                (SourceChange(ResourceKey("cases", "same", (dataset,)), dump_record(case), None),),
            )
        assert source.list_ids("cases", ("a",)) == ("same",)
        assert source.list_ids("cases", ("b",)) == ("same",)


@pytest.mark.parametrize("name", ["Cases", "unknown", "project"])
def test_external_unknown_collection_directory_rejected_even_when_empty(tmp_path, name):
    (tmp_path / "source" / name).mkdir(parents=True)
    with FileProjectSource(tmp_path) as source:
        with pytest.raises(ServiceFailure) as error:
            source.capture_snapshot()
        assert error.value.error.reason == "invalid_source_path"


def test_root_metadata_symlink_is_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(body())
    (root / "deykit.project.json").symlink_to(outside)
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure):
            source.capture_snapshot()
    assert outside.read_bytes() == body()
