"""Private anchored replacement receipts keep commit visibility truthful."""

import os
import stat

import pytest

from deykit.application.errors import ServiceFailure
from deykit.storage import _win32 as win
from deykit.storage.filesystem import SafeFiles

WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Requires native Windows handles")
POSIX = pytest.mark.skipif(os.name != "posix", reason="Requires POSIX descriptors")


@pytest.fixture
def files(tmp_path):
    instance = SafeFiles(tmp_path / "project", create=True)
    instance.replace(("source", "target"), b"old")
    try:
        yield instance
    finally:
        instance.close()


def _replace(files, body, *, before_replace=None):
    backend = files._backend
    with backend.directory(("source",)) as parent:
        return backend._replace_in(parent, "target", body, before_replace=before_replace)


def test_precommit_failure_preserves_old_bytes_and_cleans_temporary(files, monkeypatch):
    backend = files._backend
    called = []

    def fail(_):
        raise OSError("file flush failed")

    if os.name == "posix":
        monkeypatch.setattr(backend, "_flush_file", fail)
    else:
        monkeypatch.setattr(backend.api, "flush", fail)
    with pytest.raises(OSError, match="file flush failed"):
        _replace(files, b"new", before_replace=lambda: called.append(True))
    assert called == []
    assert files.read(("source", "target")) == b"old"
    assert not any(name.startswith(".tmp-") for name in files.names(("source",)))


def test_precommit_callback_failure_preserves_old_bytes_and_cleans_temp(files):
    def reject():
        raise ValueError("destination changed")

    with pytest.raises(ValueError, match="destination changed"):
        _replace(files, b"new", before_replace=reject)
    assert files.read(("source", "target")) == b"old"
    assert not any(name.startswith(".tmp-") for name in files.names(("source",)))


def test_callback_runs_before_replace_and_receipt_reports_commit(files):
    observed = []

    def callback():
        observed.append(files.read(("source", "target")))

    result = _replace(files, b"new exact bytes", before_replace=callback)
    assert observed == [b"old"]
    assert files.read(("source", "target")) == b"new exact bytes"
    assert result.post_commit_error is None
    assert result.parent_flush == ("confirmed" if os.name == "posix" else "unavailable")


@POSIX
def test_parent_flush_failure_returns_committed_receipt_and_legacy_replace_raises(
    files, monkeypatch
):
    original = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("parent flush failed")
        original(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    result = _replace(files, b"receipt body")
    assert result.parent_flush == "failed"
    assert isinstance(result.post_commit_error, OSError)
    assert files.read(("source", "target")) == b"receipt body"

    with pytest.raises(OSError, match="parent flush failed"):
        files.replace(("source", "target"), b"legacy body")
    assert files.read(("source", "target")) == b"legacy body"


@POSIX
def test_postcommit_temporary_descriptor_close_error_is_captured(files, monkeypatch):
    original_fdopen, original_close = os.fdopen, os.close
    target_fds = set()

    def fdopen(fd, *args, **kwargs):
        target_fds.add(fd)
        return original_fdopen(fd, *args, **kwargs)

    def close(fd):
        if fd in target_fds:
            target_fds.remove(fd)
            original_close(fd)
            raise OSError("temporary close failed")
        original_close(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fdopen", fdopen)
        patch.setattr(os, "close", close)
        result = _replace(files, b"visible")
    assert result.parent_flush == "confirmed"
    assert isinstance(result.post_commit_error, OSError)
    assert files.read(("source", "target")) == b"visible"


@WINDOWS
def test_windows_receipt_and_native_identity_queries(files):
    backend = files._backend
    with backend.directory(("source",)) as parent:
        identity = backend.api.identity(parent)
        final_path = backend.api.final_path(parent)
        assert len(identity) == 2 and all(type(value) is int for value in identity)
        assert final_path and final_path.endswith("source")
        assert backend.api.final_component(parent) == "source"
        result = backend._replace_in(parent, "target", b"native bytes")
    assert result.parent_flush == "unavailable"
    assert result.post_commit_error is None
    assert files.read(("source", "target")) == b"native bytes"


@WINDOWS
def test_windows_postcommit_handle_close_error_is_captured(files, monkeypatch):
    backend = files._backend
    original_close = win.Handle.close
    armed = []

    def close(handle):
        if armed and handle is armed[0]:
            armed.clear()
            original_close(handle)
            raise OSError("native temporary close failed")
        original_close(handle)

    original_open = backend.api.open

    def capture_open(parent, name, **kwargs):
        handle = original_open(parent, name, **kwargs)
        if name.startswith(".tmp-"):
            armed.append(handle)
        return handle

    monkeypatch.setattr(backend.api, "open", capture_open)
    monkeypatch.setattr(win.Handle, "close", close)
    result = _replace(files, b"visible")
    assert result.parent_flush == "unavailable"
    assert isinstance(result.post_commit_error, OSError)
    assert files.read(("source", "target")) == b"visible"


@pytest.mark.parametrize("identity_type", ["symlink", "hardlink"])
@POSIX
def test_backend_replace_keeps_existing_target_admission(files, tmp_path, identity_type):
    target = files.root / "source/target"
    outside = tmp_path / "outside"
    outside.write_bytes(b"safe")
    target.unlink()
    if identity_type == "symlink":
        target.symlink_to(outside)
    else:
        os.link(outside, target)
    with pytest.raises(ServiceFailure):
        files.replace(("source", "target"), b"unsafe")
    assert outside.read_bytes() == b"safe"
