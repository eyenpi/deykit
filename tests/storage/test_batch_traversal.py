"""Fresh anchored walks: authored bytes, real races, and operation-count oracles."""

import hashlib
import os
import subprocess
import sys
import threading

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft, LabelRecord, ProjectRecord
from deykit.storage import FileProjectSource
from deykit.storage.filesystem import SafeFiles
from deykit.storage.locks import acquire

STAMP = "2026-10-05T12:00:00Z"


class Visitor:
    def __init__(self, fail_at=None):
        self.files = []
        self.directories = []
        self.fail_at = fail_at

    def include(self, parts):
        if self.fail_at == "include":
            raise RuntimeError("injected include")
        return not parts[-1].startswith(".tmp-")

    def validate_entry(self, parts, *, directory):
        if self.fail_at == "validate":
            raise RuntimeError("injected validate")
        if directory:
            self.directories.append(parts)

    def accept_file(self, parts, body):
        if self.fail_at == "accept":
            raise RuntimeError("injected accept")
        self.files.append((parts, body))


@pytest.fixture
def files(tmp_path):
    root = tmp_path / ("Project with spaces ü " + "z" * 80)
    instance = SafeFiles(root, create=True)
    try:
        yield instance
    finally:
        instance.close()


def failure_reason(call, reason):
    with pytest.raises(ServiceFailure) as error:
        call()
    assert error.value.error.reason == reason


def after_inventory(files, monkeypatch, target_names, mutate):
    """Inject once after a real enumeration, selected by authored child names."""
    backend = files._backend
    method = "_tree_names" if os.name == "posix" else "_tree_entries"
    original = getattr(backend, method)
    fired = []

    def enumerate_once(parent):
        result = original(parent)
        names = result if os.name == "posix" else tuple(name for name, _ in result)
        if names == target_names and not fired:
            fired.append(True)
            mutate()
        return result

    monkeypatch.setattr(backend, method, enumerate_once)
    return fired


def test_exact_binary_inventory_stable_ignored_entries_and_empty_tree(files):
    paths = {
        ("source", "labels", "Decision", "Data", "a.json"): b"\x00\xff\r\nprecise",
        ("source", "labels", "Decision", "Data", "b.json"): b"9007199254740993",
    }
    for parts, body in paths.items():
        files.replace(parts, body)
    files.mkdir(("source", "empty"))
    ignored = files.root / "source/.tmp-arbitrary"
    ignored.mkdir()
    (ignored / "unsafe").write_bytes(b"never read")
    files.replace(("source", ".tmp-file"), b"ignored")
    visitor = Visitor()
    backend = files._backend
    opened = []
    if os.name == "posix":
        original_open = os.open

        def open_checked(name, *args, **kwargs):
            opened.append(name)
            assert name != ".tmp-arbitrary" and name != ".tmp-file"
            return original_open(name, *args, **kwargs)

        from _pytest.monkeypatch import MonkeyPatch

        patch = MonkeyPatch()
        patch.setattr(os, "open", open_checked)
    else:
        original_open = backend.api.open

        def open_checked(parent, name, **kwargs):
            opened.append(name)
            assert name != ".tmp-arbitrary" and name != ".tmp-file"
            return original_open(parent, name, **kwargs)

        from _pytest.monkeypatch import MonkeyPatch

        patch = MonkeyPatch()
        patch.setattr(backend.api, "open", open_checked)
    try:
        files.read_tree(("source",), visitor)
    finally:
        patch.undo()
    assert visitor.files == sorted(paths.items())
    assert ("source", "empty") in visitor.directories
    assert [hashlib.sha256(body).hexdigest() for _, body in visitor.files] == [
        hashlib.sha256(body).hexdigest() for _, body in sorted(paths.items())
    ]
    assert (ignored / "unsafe").read_bytes() == b"never read"


def test_initially_missing_and_empty_tree(files):
    visitor = Visitor()
    files.read_tree(("source",), visitor)
    files.mkdir(("source",))
    files.read_tree(("source",), visitor)
    assert visitor.files == visitor.directories == []


@pytest.mark.parametrize("change", ["add", "delete", "rename", "temporary"])
def test_exit_inventory_membership_conflict(files, monkeypatch, change):
    files.replace(("source", "leaf"), b"old")
    leaf = files.root / "source/leaf"

    def mutate():
        if change == "add":
            leaf.with_name("other").write_bytes(b"new")
        elif change == "delete":
            leaf.unlink()
        elif change == "rename":
            leaf.rename(leaf.with_name("other"))
        else:
            leaf.with_name(".tmp-changed").write_bytes(b"ignored")

    fired = after_inventory(files, monkeypatch, ("leaf",), mutate)
    failure_reason(lambda: files.read_tree(("source",), Visitor()), "unstable_source")
    assert fired == [True]


@pytest.mark.parametrize("directory", [False, True])
def test_new_casefold_collision_checked_at_exit(files, monkeypatch, directory):
    selected = files.root / "source/Case"
    files.mkdir(("source",))
    if os.name == "nt":
        import ctypes as c

        from deykit.storage import _win32 as win

        backend = files._backend
        with backend.directory(()) as root_handle:
            with backend.api.open(
                root_handle, "source", directory=True, access=win.DIRECTORY_ACCESS | 0x100
            ) as source_handle:
                flags = win.DWORD(1)
                if not backend.api._set(source_handle.value, 23, c.byref(flags), c.sizeof(flags)):
                    if c.get_last_error() == 50:
                        pytest.skip(
                            "Actual Windows volume lacks case-sensitive directory support (50)"
                        )
                    raise c.WinError(c.get_last_error())
    if directory:
        selected.mkdir()
    else:
        selected.write_bytes(b"selected")
    alternate = selected.with_name("case")
    # Probe actual filesystem case sensitivity independently before injecting.
    if alternate.exists():
        pytest.skip("selected filesystem does not support distinct casefold siblings")

    def mutate():
        if directory:
            alternate.mkdir()
        else:
            alternate.write_bytes(b"collision")

    fired = after_inventory(files, monkeypatch, ("Case",), mutate)
    failure_reason(lambda: files.read_tree(("source",), Visitor()), "casefold_collision")
    assert fired == [True]


def test_collision_in_ignored_inventory_still_rejected(files):
    files.replace(("source", ".tmp-Case"), b"one")
    alternate = files.root / "source/.tmp-case"
    if alternate.exists():
        pytest.skip("selected filesystem does not support distinct casefold siblings")
    alternate.write_bytes(b"two")
    failure_reason(lambda: files.read_tree(("source",), Visitor()), "casefold_collision")


def test_hardlink_substitution_rejected_without_target_read(files, monkeypatch, tmp_path):
    files.replace(("source", "leaf"), b"old")
    outside = tmp_path / "sentinel"
    outside.write_bytes(b"outside")

    def mutate():
        target = files.root / "source/leaf"
        target.unlink()
        os.link(outside, target)

    fired = after_inventory(files, monkeypatch, ("leaf",), mutate)
    visitor = Visitor()
    failure_reason(lambda: files.read_tree(("source",), visitor), "unsafe_source_path")
    assert fired == [True] and visitor.files == []
    assert outside.read_bytes() == b"outside"


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow descriptor race")
def test_symlink_substitution_is_rejected(files, monkeypatch, tmp_path):
    files.replace(("source", "leaf"), b"old")
    outside = tmp_path / "sentinel"
    outside.write_bytes(b"outside")

    def mutate():
        leaf = files.root / "source/leaf"
        leaf.unlink()
        leaf.symlink_to(outside)

    after_inventory(files, monkeypatch, ("leaf",), mutate)
    visitor = Visitor()
    failure_reason(lambda: files.read_tree(("source",), visitor), "unsafe_source_path")
    assert visitor.files == [] and outside.read_bytes() == b"outside"


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO race; Windows reparse tested separately")
def test_fifo_substitution_is_bounded_in_subprocess(files):
    files.replace(("source", "leaf"), b"old")
    program = r"""
import os, sys
from pathlib import Path
from deykit.storage.filesystem import SafeFiles
from deykit.application.errors import ServiceFailure
class Visitor:
    def include(self, parts): return True
    def validate_entry(self, parts, *, directory): pass
    def accept_file(self, parts, body): raise AssertionError('FIFO bytes accepted')
f = SafeFiles(Path(sys.argv[1]))
original = f._backend._tree_names
fired = False
def names(parent):
    global fired
    result = original(parent)
    if result == ('leaf',) and not fired:
        fired = True
        leaf = f.root / 'source/leaf'
        leaf.unlink()
        os.mkfifo(leaf)
    return result
f._backend._tree_names = names
try:
    f.read_tree(('source',), Visitor())
except ServiceFailure as error:
    assert error.error.reason == 'unsafe_source_path'
else:
    raise AssertionError('FIFO accepted')
f.close()
print('rejected and closed')
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(files.root)],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert result.stdout.strip() == "rejected and closed"


@pytest.mark.skipif(os.name != "posix", reason="POSIX retained-descriptor rename semantics")
def test_retained_ancestor_rename_never_reads_replacement(files, monkeypatch, tmp_path):
    files.replace(("source", "leaf"), b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leaf").write_bytes(b"outside")

    def mutate():
        source = files.root / "source"
        source.rename(files.root / "saved")
        source.symlink_to(outside, target_is_directory=True)

    after_inventory(files, monkeypatch, ("leaf",), mutate)
    visitor = Visitor()
    files.read_tree(("source",), visitor)
    assert visitor.files == [(("source", "leaf"), b"inside")]
    failure_reason(lambda: files.read_tree(("source",), Visitor()), "unsafe_source_path")
    assert (outside / "leaf").read_bytes() == b"outside"


def test_file_growth_after_size_check_stays_bounded_and_fails(files, monkeypatch):
    if os.name != "posix":
        pytest.skip("The growth injection uses a POSIX descriptor")
    files.replace(("source", "leaf"), b"x")
    original_fdopen = os.fdopen
    requested = []

    class BoundedStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size=-1):
            requested.append(size)
            assert size == 5
            return self.stream.read(size)

    def grow_after_fstat(fd, *args, **kwargs):
        stream = original_fdopen(fd, *args, **kwargs)
        path = files.root / "source/leaf"
        with path.open("wb") as external:
            external.write(b"12345678")
        return BoundedStream(stream)

    monkeypatch.setattr(os, "fdopen", grow_after_fstat)
    failure_reason(
        lambda: files.read_tree(("source",), Visitor(), limit=4), "record_resource_limit"
    )
    assert requested == [5]


@pytest.mark.parametrize(
    "limit,body,expected",
    [
        (0, b"", None),
        (0, b"x", "record_resource_limit"),
        (-1, b"", "record_resource_limit"),
        (2, b"abc", "record_resource_limit"),
    ],
)
def test_limits(files, limit, body, expected):
    files.replace(("source", "leaf"), body)
    visitor = Visitor()
    if expected:
        failure_reason(lambda: files.read_tree(("source",), visitor, limit=limit), expected)
    else:
        files.read_tree(("source",), visitor, limit=limit)
        assert visitor.files == [(("source", "leaf"), body)]


@pytest.mark.parametrize("phase", ["include", "validate", "accept", "enumerate", "open", "read"])
def test_failure_cleanup_allows_fresh_read_and_lock(files, monkeypatch, phase):
    files.replace(("source", "leaf"), b"old")
    backend = files._backend
    with monkeypatch.context() as patch:
        if phase in {"enumerate", "open", "read"}:
            if phase == "enumerate":
                target, method = backend, "_tree_names" if os.name == "posix" else "_tree_entries"
            elif os.name == "posix":
                target, method = (os, "open") if phase == "open" else (backend, "_read_open_file")
            else:
                target, method = backend.api, phase

            def broken(*args, **kwargs):
                raise OSError("injected " + phase)

            patch.setattr(target, method, broken)
            with pytest.raises(OSError, match="injected"):
                files.read_tree(("source",), Visitor())
        else:
            with pytest.raises(RuntimeError, match="injected"):
                files.read_tree(("source",), Visitor(phase))
    visitor = Visitor()
    files.read_tree(("source",), visitor)
    assert visitor.files == [(("source", "leaf"), b"old")]
    with acquire(files, "source.lock"):
        assert files.read(("source", "leaf")) == b"old"


def instrument(files, monkeypatch):
    """Count real operations and live traversal resources, forwarding every call."""
    stats = {"enumerations": 0, "opens": 0, "duplicates": 0, "peak": 0, "live": 0}
    if os.name == "posix":
        original_open, original_dup, original_close, original_list = (
            os.open,
            os.dup,
            os.close,
            os.listdir,
        )
        owned = set()

        def register(fd):
            assert not os.get_inheritable(fd)
            owned.add(fd)
            stats["live"] = len(owned)
            stats["peak"] = max(stats["peak"], len(owned))
            return fd

        def opening(*args, **kwargs):
            stats["opens"] += 1
            return register(original_open(*args, **kwargs))

        def duplicate(*args, **kwargs):
            stats["duplicates"] += 1
            return register(original_dup(*args, **kwargs))

        def close(fd):
            original_close(fd)
            owned.discard(fd)
            stats["live"] = len(owned)

        def names(*args, **kwargs):
            stats["enumerations"] += 1
            return original_list(*args, **kwargs)

        monkeypatch.setattr(os, "open", opening)
        monkeypatch.setattr(os, "dup", duplicate)
        monkeypatch.setattr(os, "close", close)
        monkeypatch.setattr(os, "listdir", names)
    else:
        import ctypes as c

        from deykit.storage import _win32 as win

        api = files._backend.api
        original_open, original_dup, original_entries = api.open, api.duplicate, api.entries
        original_close = win.Handle.close
        owned = set()
        flags_query = api._bind(
            api._kernel, "GetHandleInformation", c.c_int, [win.HANDLE, c.POINTER(win.DWORD)]
        )

        def register(handle):
            flags = win.DWORD()
            api._check(flags_query(handle.value, c.byref(flags)))
            assert not flags.value & 1
            owned.add(id(handle))
            stats["live"] = len(owned)
            stats["peak"] = max(stats["peak"], len(owned))
            return handle

        def opening(*args, **kwargs):
            stats["opens"] += 1
            return register(original_open(*args, **kwargs))

        def duplicate(*args, **kwargs):
            stats["duplicates"] += 1
            return register(original_dup(*args, **kwargs))

        def close(handle):
            original_close(handle)
            owned.discard(id(handle))
            stats["live"] = len(owned)

        def entries(*args, **kwargs):
            stats["enumerations"] += 1
            return original_entries(*args, **kwargs)

        monkeypatch.setattr(api, "open", opening)
        monkeypatch.setattr(api, "duplicate", duplicate)
        monkeypatch.setattr(api, "entries", entries)
        monkeypatch.setattr(win.Handle, "close", close)
    return stats


@pytest.mark.parametrize("count", [10, 1000])
def test_directory_linear_counts_and_independent_repeat(files, monkeypatch, count):
    expected = []
    folder = files.root / "source/labels/Decision/Data"
    folder.mkdir(parents=True)
    for i in range(count):
        name = f"{i:04d}.json"
        body = f"authored {i}".encode()
        (folder / name).write_bytes(body)
        expected.append((("source", "labels", "Decision", "Data", name), body))
    stats = instrument(files, monkeypatch)
    results = []
    for _ in range(2):
        stats.update(dict.fromkeys(stats, 0))
        visitor = Visitor()
        files.read_tree(("source",), visitor)
        assert visitor.files == expected
        assert stats == {
            "enumerations": 9,
            "opens": count + 4,
            "duplicates": 1,
            "peak": 6,
            "live": 0,
        }
        results.append(dict(stats))
    assert results[0] == results[1]


def test_branching_topology_counts(files, monkeypatch):
    for directory in ("a", "b", "c"):
        files.replace(("source", directory, "leaf"), directory.encode())
    stats = instrument(files, monkeypatch)
    visitor = Visitor()
    files.read_tree(("source",), visitor)
    assert stats == {"enumerations": 9, "opens": 7, "duplicates": 1, "peak": 4, "live": 0}
    assert visitor.files == [(("source", name, "leaf"), name.encode()) for name in ("a", "b", "c")]


def test_visitor_failure_closes_all_instrumented_resources(files, monkeypatch):
    files.replace(("source", "folder", "leaf"), b"old")
    stats = instrument(files, monkeypatch)
    with pytest.raises(RuntimeError):
        files.read_tree(("source",), Visitor("accept"))
    assert stats["live"] == 0


def test_other_thread_close_waits_for_visitor_cleanup(files):
    files.replace(("source", "leaf"), b"old")
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    errors = []

    class BlockingVisitor(Visitor):
        def accept_file(self, parts, body):
            entered.set()
            assert release.wait(5)
            super().accept_file(parts, body)

    visitor = BlockingVisitor()

    def walk():
        try:
            files.read_tree(("source",), visitor)
        except BaseException as error:
            errors.append(error)

    def close():
        files.close()
        closed.set()

    walker = threading.Thread(target=walk)
    walker.start()
    closer = threading.Thread(target=close)
    try:
        assert entered.wait(5)
        closer.start()
        assert not closed.wait(0.05)
    finally:
        release.set()
        walker.join(5)
        if closer.ident is not None:
            closer.join(5)
    assert not walker.is_alive() and not closer.is_alive()
    assert errors == [] and closed.is_set()
    assert visitor.files == [(("source", "leaf"), b"old")]
    failure_reason(lambda: files.read_tree(("source",), Visitor()), "storage_closed")


def initialized(tmp_path):
    root = tmp_path / "Source ü"
    root.mkdir()
    (root / "deykit.project.json").write_bytes(
        dump_record(ProjectRecord(id="p", name="Old", created_at=STAMP))
    )
    return root


def draft(text):
    return dump_record(DecisionDraft(decision_id="d", editor_source=text, updated_at=STAMP))


@pytest.mark.parametrize(
    "path",
    [
        ("source", "unknown"),
        ("source", "project"),
        ("source", "drafts", "extra"),
        ("source", "labels", "Decision", "Data", "extra"),
        ("source", "cases", "bad.scope"),
    ],
)
def test_invalid_empty_source_directory_rejected_before_bytes(tmp_path, path):
    root = initialized(tmp_path)
    root.joinpath(*path).mkdir(parents=True)
    with FileProjectSource(root) as source:
        failure_reason(source.capture_snapshot, "invalid_source_path")
    assert not (root / "history/journal").exists()


def test_all_accepts_typed_labels_and_sorted_exact_bodies(tmp_path):
    root = initialized(tmp_path)
    folder = root / "source/labels/Decision/Data"
    folder.mkdir(parents=True)
    authored = []
    for name in ("z", "a"):
        body = dump_record(
            LabelRecord(
                id=name,
                decision_id="Decision",
                dataset_id="Data",
                case_id=name,
                question_id="q",
                input_hash="a" * 64,
                acceptable_option_ids=("yes",),
                provenance="human",
                updated_at=STAMP,
            )
        )
        (folder / f"{name}.json").write_bytes(body)
        authored.append((name, body))
    with FileProjectSource(root) as source:
        labels = [
            record for record in source.capture_snapshot() if record.key.collection == "labels"
        ]
        assert [(record.key.resource_id, record.body) for record in labels] == sorted(authored)
        assert all(record.etag == hashlib.sha256(record.body).hexdigest() for record in labels)


@pytest.mark.parametrize("target", ["draft", "marker"])
def test_same_length_restored_timestamp_edit_conflicts_in_fresh_snapshot(
    tmp_path, monkeypatch, target
):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as source:
        source.commit("initial", (SourceChange(key, draft("before"), None),))
    path = root / ("source/drafts/d.json" if target == "draft" else "deykit.project.json")
    before = path.read_bytes()
    after = draft("AFTER!") if target == "draft" else before.replace(b'"Old"', b'"New"')
    assert len(after) == len(before) and after != before
    stat = path.stat()
    events = []

    def hook(point):
        if point == "snapshot_captured":
            assert events[-1] == "walk_closed"
            events.append("hook")
            path.write_bytes(after)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            assert path.stat().st_mtime_ns == stat.st_mtime_ns
            assert path.read_bytes() == after

    with FileProjectSource(root, fault_hook=hook) as source:
        original = source.files.read_tree

        def walk(*args, **kwargs):
            events.append("walk_opened")
            try:
                return original(*args, **kwargs)
            finally:
                events.append("walk_closed")

        monkeypatch.setattr(source.files, "read_tree", walk)
        failure_reason(source.capture_snapshot, "unstable_source")
    index = events.index("hook")
    assert events[index - 2 : index + 3] == [
        "walk_opened",
        "walk_closed",
        "hook",
        "walk_opened",
        "walk_closed",
    ]
    assert path.read_bytes() == after


def test_prepared_external_edit_is_not_overwritten_and_staging_discards(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as source:
        saved = source.commit("initial", (SourceChange(key, draft("before"), None),)).changes[0]
    path = root / "source/drafts/d.json"
    stat = path.stat()
    external = draft("AFTER!")
    assert len(external) == len(saved.body)

    def hook(point):
        if point == "prepared":
            path.write_bytes(external)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    with FileProjectSource(root, fault_hook=hook) as source:
        failure_reason(
            lambda: source.commit("changed", (SourceChange(key, draft("proposed"), saved.etag),)),
            "unstable_source",
        )
    assert path.read_bytes() == external
    assert not (root / "history/journal/changed/commit.json").exists()
    assert not (root / "history/operations/changed").exists()
    with FileProjectSource(root) as source:
        assert source.read(key).body == external
    assert not (root / "history/journal/changed").exists()
    assert path.read_bytes() == external


def test_reentrant_prepared_failure_discards_and_preserves_old_source(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")

    def hook(point):
        if point == "prepared":
            raise OSError("prepared failure")

    with FileProjectSource(root, fault_hook=hook) as source:
        with source.consistent_read():
            failure_reason(
                lambda: source.commit("failed", (SourceChange(key, draft("proposed"), None),)),
                "storage_io",
            )
            assert source.read(key) is None
            assert not (root / "history/journal/failed").exists()
