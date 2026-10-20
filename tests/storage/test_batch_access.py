"""Batch accesses keep path safety and avoid per-record sibling scans."""

import os
from contextlib import closing

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft
from deykit.storage import FileProjectSource
from deykit.storage.filesystem import SafeFiles


def draft(index, text):
    return dump_record(
        DecisionDraft(
            decision_id=f"draft-{index}", editor_source=text, updated_at="2026-10-20T00:00:00Z"
        )
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor enumeration probe")
def test_commit_does_not_enumerate_siblings_per_changed_record(tmp_path, monkeypatch):
    with FileProjectSource(tmp_path / "project", create=True) as source:
        saved = source.commit(
            "seed",
            tuple(
                SourceChange(ResourceKey("drafts", f"draft-{i}"), draft(i, "before"), None)
                for i in range(100)
            ),
        ).changes
        identity = (source.root / "source/drafts").stat().st_ino
        listings = []
        listdir = os.listdir

        def observe(path):
            if isinstance(path, int) and os.fstat(path).st_ino == identity:
                listings.append(path)
            return listdir(path)

        monkeypatch.setattr(os, "listdir", observe)
        changes = tuple(
            SourceChange(record.key, draft(int(record.key.resource_id[6:]), "after"), record.etag)
            for record in saved[:16]
        )
        result = source.commit("edit", changes)
        assert tuple(record.body for record in result.changes) == tuple(c.body for c in changes)
        assert len(listings) <= 16


def test_read_many_selects_exact_paths_and_checks_aliases(tmp_path):
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:
        files.replace(("scope", "one"), b"one")
        files.replace(("scope", "two"), b"two")
        assert files.read_many((("scope", "one"), ("scope", "missing"))) == {
            ("scope", "one"): b"one"
        }
        with pytest.raises(ServiceFailure) as failure:
            files.read_many((("SCOPE", "one"),))
        assert failure.value.error.reason == "casefold_collision"


def test_apply_many_preserves_order_and_partial_failure(tmp_path):
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:
        seen = []

        def interrupt(index):
            seen.append(index)
            if index == 1:
                raise OSError("authored interruption")

        with pytest.raises(OSError, match="authored interruption"):
            files.apply_many(
                (
                    (("scope", "z"), b"first"),
                    (("scope", "a"), b"second"),
                    (("scope", "last"), b"never"),
                ),
                after_write=interrupt,
            )
        assert seen == [0, 1]
        assert files.read(("scope", "z")) == b"first"
        assert files.read(("scope", "a")) == b"second"
        assert files.read(("scope", "last")) is None
        files.apply_many(((("scope", "a"), None), (("other", "b"), b"third")))
        assert files.read(("scope", "a")) is None
        assert files.read(("other", "b")) == b"third"


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink probe")
def test_batch_access_cannot_follow_a_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "record").write_bytes(b"untouched")
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:
        (files.root / "scope").symlink_to(outside, target_is_directory=True)
        for action in (
            lambda: files.read_many((("scope", "record"),)),
            lambda: files.apply_many(((("scope", "record"), b"changed"),)),
        ):
            with pytest.raises((ServiceFailure, OSError)):
                action()
        assert (outside / "record").read_bytes() == b"untouched"


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored write probe")
def test_batch_retains_parent_anchor_after_path_replacement(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "second").write_bytes(b"untouched")
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:

        def swap(index):
            if index == 0:
                os.rename(files.root / "scope", files.root / "moved")
                (files.root / "scope").symlink_to(outside, target_is_directory=True)

        files.apply_many(
            ((("scope", "first"), b"first"), (("scope", "second"), b"second")), after_write=swap
        )
        assert (outside / "second").read_bytes() == b"untouched"
        assert (files.root / "moved/second").read_bytes() == b"second"


@pytest.mark.skipif(os.name != "posix", reason="POSIX link replacement probe")
@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_batch_rechecks_each_target_after_a_callback(tmp_path, kind):
    outside = tmp_path / "outside"
    outside.write_bytes(b"untouched")
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:

        def substitute(index):
            if index == 0:
                path = files.root / "scope/second"
                if kind == "symlink":
                    path.symlink_to(outside)
                else:
                    os.link(outside, path)

        with pytest.raises(ServiceFailure):
            files.apply_many(
                ((("scope", "first"), b"first"), (("scope", "second"), b"second")),
                after_write=substitute,
            )
        assert outside.read_bytes() == b"untouched"


def test_batch_rechecks_requested_spelling_on_exit(tmp_path):
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:

        def rename(index):
            os.rename(files.root / "scope/record", files.root / "scope/RECORD")

        with pytest.raises(ServiceFailure) as failure:
            files.apply_many(((("scope", "record"), b"record"),), after_write=rename)
        assert failure.value.error.reason == "casefold_collision"


def test_batch_access_ignores_unrelated_root_case_aliases(tmp_path):
    with closing(SafeFiles(tmp_path / "files", create=True)) as files:
        (files.root / "readme").write_bytes(b"one")
        (files.root / "README").write_bytes(b"two")
        files.apply_many(((("scope", "record"), b"record"),))
        assert files.read_many((("scope", "record"),)) == {("scope", "record"): b"record"}
