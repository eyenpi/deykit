"""A nested source boundary must not repeat recovery of an unchanged journal."""

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft
from deykit.storage import FileProjectSource


def test_nested_reads_recover_only_once(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        recovered = []
        original = source._recover

        def recover():
            recovered.append(True)
            return original()

        monkeypatch.setattr(source, "_recover", recover)
        with source.consistent_read():
            source.capture_snapshot()
            source.list_ids("drafts")
            source.read(ResourceKey("drafts", "draft"))
        assert len(recovered) == 1


def test_nested_read_recovers_after_caught_commit_failure(tmp_path):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        key = ResourceKey("drafts", "draft")
        body = dump_record(
            DecisionDraft(
                decision_id="draft", editor_source="authored", updated_at="2026-10-19T00:00:00Z"
            )
        )
        with source.consistent_read():

            def stop(stage):
                if stage == "decided":
                    raise OSError("injected interruption")

            source._hook = stop
            with pytest.raises(ServiceFailure):
                source.commit("interrupted", (SourceChange(key, body, None),))
            source._hook = lambda _: None
            assert source.read(key).body == body


def test_nested_reads_share_the_validated_source_epoch(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "epoch", create=True) as source:
        walks = []
        read_tree = source.files.read_tree

        def observe(parts, visitor, **kwargs):
            if parts == ("source",):
                walks.append(parts)
            return read_tree(parts, visitor, **kwargs)

        monkeypatch.setattr(source.files, "read_tree", observe)
        with source.consistent_read():
            source.read(ResourceKey("drafts", "first"))
            source.read(ResourceKey("drafts", "second"))
            source.list_ids("drafts")
        assert len(walks) == 1


def test_visible_archive_failure_invalidates_the_entered_epoch(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "archive-error", create=True) as source:
        key = ResourceKey("drafts", "draft")
        before = dump_record(
            DecisionDraft(
                decision_id="draft", editor_source="before", updated_at="2026-10-19T00:00:00Z"
            )
        )
        after = dump_record(
            DecisionDraft(
                decision_id="draft", editor_source="after", updated_at="2026-10-19T00:00:00Z"
            )
        )
        saved = source.commit("initial", (SourceChange(key, before, None),)).changes[0]
        rename = source.files.rename_directory

        def visible_failure(old, new):
            rename(old, new)
            raise OSError("injected error after visible archival rename")

        with source.consistent_read():
            monkeypatch.setattr(source.files, "rename_directory", visible_failure)
            with pytest.raises(ServiceFailure):
                source.commit("changed", (SourceChange(key, after, saved.etag),))
            monkeypatch.setattr(source.files, "rename_directory", rename)
            assert source.read(key).body == after


def test_commit_reuses_the_freshly_validated_history_sequence(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "sequence", create=True) as source:
        key = ResourceKey("drafts", "draft")
        body = dump_record(
            DecisionDraft(
                decision_id="draft", editor_source="authored", updated_at="2026-10-19T00:00:00Z"
            )
        )
        saved = source.commit("first", (SourceChange(key, body, None),)).changes[0]
        source.read(key)
        calls = []
        manifest = source._manifest

        def observe(folder):
            calls.append(folder)
            return manifest(folder)

        monkeypatch.setattr(source, "_manifest", observe)
        source.commit("second", (SourceChange(key, body, saved.etag),))
        assert calls == []


def test_nested_error_drops_the_cached_integrity_view(tmp_path):
    with FileProjectSource(tmp_path / "invalidated", create=True) as source:
        key = ResourceKey("drafts", "draft")
        body = dump_record(
            DecisionDraft(
                decision_id="draft", editor_source="authored", updated_at="2026-10-19T00:00:00Z"
            )
        )
        saved = source.commit("first", (SourceChange(key, body, None),)).changes[0]

        def damage_after_archive(point):
            if point == "archived":
                (source.root / "history/operations/changed/new-0.json").write_bytes(b"damaged")
                raise OSError("injected archival failure")

        with source.consistent_read():
            source._hook = damage_after_archive
            with pytest.raises(ServiceFailure):
                source.commit("changed", (SourceChange(key, body, saved.etag),))
            source._hook = lambda _: None
            with pytest.raises(ServiceFailure) as failure:
                source.read(key)
            assert failure.value.error.reason == "journal_integrity_error"
