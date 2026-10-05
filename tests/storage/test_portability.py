"""Real-host storage acceptance. Windows-only cases execute on hosted Windows CI."""

import importlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deykit.application.errors import ServiceFailure
from deykit.storage.filesystem import SafeFiles
from deykit.storage.locks import acquire

WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Requires actual Win32 handles and local NTFS")
POSIX = pytest.mark.skipif(os.name != "posix", reason="Requires actual POSIX descriptors")


@pytest.fixture
def files(tmp_path):
    instance = SafeFiles(tmp_path / "project", create=True)
    try:
        yield instance
    finally:
        instance.close()


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../outside",
        "a/b",
        "a\\b",
        "C:outside",
        "x:stream",
        "nul",
        "CON.json",
        "LPT1",
        "COM9.log",
        "com¹",
        "a.",
        "a ",
        "x\x00y",
        "x?y",
        "\\\\.\\NUL",
    ],
)
def test_internal_aliases_rejected_without_touching_sentinel(files, tmp_path, name):
    sentinel = tmp_path / "outside"
    sentinel.write_bytes(b"outside sentinel")
    for action in (
        lambda: files.read((name,)),
        lambda: files.replace((name,), b"bad"),
        lambda: files.unlink((name,)),
        lambda: files.mkdir((name,)),
        lambda: files.check_path_spelling((name,)),
        lambda: files.names((name,)),
    ):
        with pytest.raises(ServiceFailure):
            action()
    assert sentinel.read_bytes() == b"outside sentinel"
    assert files.names(()) == ()


def test_binary_bytes_long_unicode_root_and_atomic_replacement(tmp_path):
    root = tmp_path / "space فارسی café" / ("a" * 80) / ("b" * 80) / ("c" * 80)
    instance = SafeFiles(root, create=True)
    try:
        body = b'\x00\xff\r\n{"n":9007199254740993.0000000000000000001}\n'
        instance.replace(("source", "value.json"), b"old")
        instance.replace(("source", "value.json"), body)
        assert instance.read(("source", "value.json")) == body
        assert instance.names(("source",)) == ("value.json",)
        assert instance.read(("source", "value.json"), limit=len(body)) == body
        with pytest.raises(ServiceFailure) as error:
            instance.read(("source", "value.json"), limit=len(body) - 1)
        assert error.value.error.reason == "record_resource_limit"
    finally:
        instance.close()


def test_case_collision_in_empty_scope_and_leaf(files):
    files.mkdir(("source", "Empty"))
    for action in (
        lambda: files.mkdir(("source", "empty")),
        lambda: files.check_path_spelling(("source", "empty", "c.json")),
        lambda: files.replace(("source", "empty", "c.json"), b"bad"),
    ):
        with pytest.raises(ServiceFailure) as error:
            action()
        assert error.value.error.reason == "casefold_collision"
    files.replace(("source", "Case.json"), b"old")
    with pytest.raises(ServiceFailure):
        files.replace(("source", "case.json"), b"bad")
    assert files.read(("source", "Case.json")) == b"old"


def test_closed_operations_cannot_use_recycled_descriptor(tmp_path):
    root, outside = tmp_path / "project", tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"safe")
    instance = SafeFiles(root, create=True)
    old_fd = getattr(instance._backend, "fd", None)
    instance.close()
    instance.close()
    replacement = None
    if os.name == "posix":
        replacement = os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
        if replacement != old_fd:
            os.dup2(replacement, old_fd)
            os.close(replacement)
            replacement = old_fd
    try:
        for action in (
            lambda: instance.mkdir(("bad",)),
            lambda: instance.names(()),
            lambda: instance.read(("sentinel",)),
            lambda: instance.replace(("sentinel",), b"bad"),
            lambda: instance.unlink(("sentinel",)),
            lambda: instance.is_directory(("sentinel",)),
            lambda: instance.rename_directory(("old",), ("new",)),
            lambda: instance.remove_directory(("sentinel",)),
            lambda: instance.check_path_spelling(()),
        ):
            with pytest.raises(ServiceFailure) as error:
                action()
            assert error.value.error.reason == "storage_closed"
        with pytest.raises(ServiceFailure):
            with acquire(instance, "source.lock"):
                pytest.fail("closed instance acquired ownership")
        assert sorted(item.name for item in outside.iterdir()) == ["sentinel"]
        assert (outside / "sentinel").read_bytes() == b"safe"
    finally:
        if replacement is not None:
            os.close(replacement)


@pytest.mark.parametrize(
    "path",
    [
        ("source", "record.json"),
        ("history", "record.json"),
        (".deykit", "index.sqlite3"),
        (".deykit", "locks", "source.lock"),
    ],
)
def test_hardlinks_rejected_for_every_file_role(files, tmp_path, path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"safe")
    files.mkdir(path[:-1])
    os.link(sentinel, files.root.joinpath(*path))
    for action in (
        lambda: files.read(path),
        lambda: files.replace(path, b"bad"),
        lambda: files.unlink(path),
    ):
        with pytest.raises(ServiceFailure):
            action()
    if path[-1] == "source.lock":
        with pytest.raises(ServiceFailure):
            with acquire(files, "source.lock"):
                pytest.fail("hardlinked lock accepted")
    assert sentinel.read_bytes() == b"safe"


def test_exception_releases_ownership_and_child_does_not_inherit_it(files):
    child = None
    try:
        with pytest.raises(RuntimeError):
            with acquire(files, "execution.lock", execution=True):
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        "import sys; print('ready',flush=True); sys.stdin.read()",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    close_fds=False,
                )
                assert child.stdout.readline() == b"ready\n"
                raise RuntimeError("test release")
        assert child.poll() is None
        with acquire(files, "execution.lock", execution=True):
            pass
    finally:
        if child is not None:
            child.communicate(timeout=10)


OWNER = """
import sys
from pathlib import Path
from deykit.storage.filesystem import SafeFiles
from deykit.storage.locks import acquire
files = SafeFiles(Path(sys.argv[1]))
with acquire(files, 'execution.lock', execution=True):
    print('ready', flush=True)
    sys.stdin.read()
"""


def test_cross_process_source_independence_and_killed_owner(files):
    child = subprocess.Popen(
        [sys.executable, "-c", OWNER, str(files.root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert child.stdout.readline() == b"ready\n"
        with pytest.raises(ServiceFailure) as error:
            with acquire(files, "execution.lock", execution=True):
                pytest.fail("two execution owners")
        assert error.value.error.reason == "execution_owned"
        with acquire(files, "source.lock"):
            files.replace(("history", "cancel.json"), b'{"cancel":true}')
        child.kill()
        child.wait(timeout=10)
        deadline = time.monotonic() + 10
        while True:
            try:
                with acquire(files, "execution.lock", execution=True):
                    assert files.read(("history", "cancel.json")) == b'{"cancel":true}'
                break
            except ServiceFailure as error:
                if error.error.reason != "execution_owned" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_native_module_import_is_portable():
    module = importlib.import_module("deykit.storage._win32")
    if os.name != "nt":
        with pytest.raises(OSError):
            module.Native()


@WINDOWS
@pytest.mark.parametrize("location", ["source", "history", ".deykit", ".deykit/locks"])
def test_junction_rejection_preserves_outside_sentinel(tmp_path, location):
    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"safe")
    link = root / location
    link.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
    )
    instance = SafeFiles(root)
    try:
        with pytest.raises((ServiceFailure, OSError)):
            instance.replace((*Path(location).parts, "sentinel"), b"bad")
        assert sentinel.read_bytes() == b"safe"
        assert sorted(p.name for p in outside.iterdir()) == ["sentinel"]
    finally:
        instance.close()
        link.rmdir()


@WINDOWS
def test_reparse_root_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root), str(outside)], check=True, capture_output=True
    )
    try:
        with pytest.raises(ServiceFailure):
            SafeFiles(root)
    finally:
        root.rmdir()


@WINDOWS
def test_sharing_and_parent_guards(files):
    from deykit.storage import _win32 as win

    files.replace(("scope", "record"), b"old")
    backend = files._backend
    with backend.directory(("scope",)) as parent:
        with pytest.raises(OSError):
            os.rename(files.root / "scope", files.root / "moved")
        with backend.api.open(parent, "record", share=win.SHARE_RW):
            with pytest.raises(OSError):
                files.replace(("scope", "record"), b"blocked")
        assert files.read(("scope", "record")) == b"old"
        assert files.names(("scope",)) == ("record",)
    files.replace(("scope", "record"), b"new")
    assert files.read(("scope", "record")) == b"new"


@WINDOWS
def test_native_lock_errors_are_not_contention_and_handles_close_once(files, monkeypatch):
    import ctypes as c

    backend = files._backend
    with backend.directory(()) as directory:
        backend.api.inspect(directory, directory=True)
    directory.close()
    with pytest.raises(OSError):
        backend.api.inspect(directory)
    with monkeypatch.context() as patch:

        def denied(*args):
            c.set_last_error(5)
            return 0

        patch.setattr(backend.api, "_lock", denied)
        with pytest.raises(OSError) as error:
            with acquire(files, "source.lock"):
                pytest.fail("access denied became ownership")
        assert error.value.winerror == 5
    with acquire(files, "source.lock"):
        pass


@pytest.mark.parametrize("file_root", [False, True])
def test_unavailable_root_is_a_service_error(tmp_path, file_root):
    path = tmp_path / "missing"
    if file_root:
        path.write_bytes(b"not a directory")
    with pytest.raises(ServiceFailure) as error:
        SafeFiles(path)
    assert error.value.error.reason == "project_unavailable"


@WINDOWS
def test_custom_ntfs_short_alias_is_rejected_before_staging(files):
    import ctypes as c

    from deykit.storage import _win32 as win

    backend = files._backend
    files.mkdir(("longdatasetname",))
    with backend.directory(()) as parent:
        with backend.api.open(
            parent, "longdatasetname", directory=True, access=win.DIRECTORY_ACCESS | win.DELETE
        ) as handle:
            # SetFileShortName requires a case-insensitive handle. Open a test-only
            # handle through CreateFileW; production never uses it for traversal.
            raw = backend.api._create(
                str(files.root / "longdatasetname"),
                win.DELETE,
                win.SHARE_ALL,
                None,
                3,
                0x02000000,
                None,
            )
            assert raw != win.HANDLE(-1).value
            with win.Handle(backend.api, raw) as alias_handle:
                setter = backend.api._bind(
                    backend.api._kernel, "SetFileShortNameW", c.c_int, [win.HANDLE, c.c_wchar_p]
                )
                backend.api._check(setter(alias_handle.value, "SCOPEDIR"))
            assert backend.api.inspect(handle).directory
    for action in (
        lambda: files.check_path_spelling(("SCOPEDIR", "record.json")),
        lambda: files.replace(("SCOPEDIR", "record.json"), b"bad"),
        lambda: files.read(("SCOPEDIR", "record.json")),
    ):
        with pytest.raises(ServiceFailure) as error:
            action()
        assert error.value.error.reason == "casefold_collision"
    assert files.names(("longdatasetname",)) == ()


@WINDOWS
def test_native_handle_noninheritance_and_failure_loops(files, monkeypatch):
    import ctypes as c

    from deykit.storage import _win32 as win

    api = files._backend.api
    count_handles = api._bind(
        api._kernel, "GetProcessHandleCount", c.c_int, [win.HANDLE, c.POINTER(win.DWORD)]
    )
    handle_flags = api._bind(
        api._kernel, "GetHandleInformation", c.c_int, [win.HANDLE, c.POINTER(win.DWORD)]
    )

    def count():
        total = win.DWORD()
        api._check(count_handles(api._process(), c.byref(total)))
        return total.value

    with files._backend.directory(()) as handle:
        flags = win.DWORD()
        api._check(handle_flags(handle.value, c.byref(flags)))
        assert not flags.value & 1  # HANDLE_FLAG_INHERIT
    before = count()
    files.replace(("record",), b"old")
    for _ in range(20):
        with monkeypatch.context() as patch:

            def broken_flush(handle):
                raise OSError("injected flush failure")

            patch.setattr(api, "flush", broken_flush)
            with pytest.raises(OSError):
                files.replace(("record",), b"new")
        assert files.read(("record",)) == b"old"
    assert count() <= before + 2
    assert files.names(()) == ("record",)
