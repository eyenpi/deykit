"""Native exact-byte export behavior and pre/post-commit fault oracles."""

import os
import stat
import threading
from pathlib import Path

import pytest

from deykit.contracts.artifacts import ArtifactWriteOutcome
from deykit.contracts.errors import ServiceError
from deykit.storage._filesystem_posix import PosixFiles
from deykit.storage.artifact_export import NativeArtifactWriter


def _successful(outcome: ArtifactWriteOutcome) -> None:
    assert outcome.success is True
    assert outcome.destination is not None
    assert outcome.error is None


def _failed(outcome: ArtifactWriteOutcome) -> None:
    assert outcome.success is False
    assert outcome.destination is None
    assert outcome.error is not None
    assert outcome.durability_warning is None


def test_writer_replaces_exact_bytes_and_missing_parent_fails(tmp_path):
    destination = tmp_path / "nested" / "report.json"
    destination.parent.mkdir()
    destination.write_bytes(b"old bytes\x00")

    outcome = NativeArtifactWriter().write(str(destination), b'{"report":1}\n\xff')

    _successful(outcome)
    assert Path(outcome.destination) == destination
    assert destination.read_bytes() == b'{"report":1}\n\xff'

    missing = NativeArtifactWriter().write(str(tmp_path / "absent" / "report.json"), b"content")
    _failed(missing)
    assert missing.error.reason == "export_parent_missing"


@pytest.mark.parametrize("protected_name", ["source", "history", ".deykit"])
def test_protects_project_trees_even_when_child_is_absent(tmp_path, protected_name):
    project = tmp_path / "project"
    project.mkdir()
    protected_directory = project / protected_name
    protected_directory.mkdir()
    protected_child = protected_directory / "not-created"
    outcome = NativeArtifactWriter((project,)).write(str(protected_child), b"replacement")

    _failed(outcome)
    assert outcome.error.reason == "export_destination_protected"
    assert not protected_child.exists()


def test_protects_manifest_and_existing_project_data_but_allows_reports_and_external(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    paths = {
        project / "deykit.project.json": b"manifest bytes",
        project / "source" / "record.json": b"source bytes",
        project / "history" / "event.json": b"history bytes",
        project / ".deykit" / "index": b"index bytes",
    }
    for path, original in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)

    writer = NativeArtifactWriter((project,))
    for path, original in paths.items():
        _failed(writer.write(str(path), b"replacement"))
        assert path.read_bytes() == original

    reports = project / "reports" / "evidence.json"
    reports.parent.mkdir()
    external = tmp_path / "outside" / "report.bin"
    external.parent.mkdir()
    _successful(writer.write(str(reports), b"report bytes"))
    _successful(writer.write(str(external), b"external bytes"))
    assert reports.read_bytes() == b"report bytes"
    assert external.read_bytes() == b"external bytes"


@pytest.mark.parametrize("path_kind", ["traversal", "missing", "directory", "symlink", "hardlink"])
def test_invalid_destinations_preserve_existing_targets(tmp_path, path_kind):
    target = tmp_path / "target.bin"
    target.write_bytes(b"original target")
    if path_kind == "traversal":
        destination = str(tmp_path / ".." / "outside.bin")
    elif path_kind == "missing":
        destination = str(tmp_path / "missing" / "report.bin")
    elif path_kind == "directory":
        destination = str(tmp_path)
    elif path_kind == "symlink":
        destination = str(tmp_path / "link.bin")
        Path(destination).symlink_to(target)
    else:
        destination = str(tmp_path / "hardlink.bin")
        os.link(target, destination)

    outcome = NativeArtifactWriter().write(destination, b"replacement")

    _failed(outcome)
    assert target.read_bytes() == b"original target"
    if path_kind in {"symlink", "hardlink"}:
        assert Path(destination).exists()
    assert not tuple(path for path in tmp_path.iterdir() if path.name.startswith(".tmp-"))


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX directory descriptors.")
def test_parent_rebinding_never_redirects_the_anchored_write(tmp_path, monkeypatch):
    parent = tmp_path / "output"
    moved_parent = tmp_path / "moved-output"
    redirect = tmp_path / "redirect"
    parent.mkdir()
    redirect.mkdir()
    original_replace_in = PosixFiles._replace_in

    def move_after_admission(self, parent_fd, leaf, body, *, before_replace=None):
        def rebind() -> None:
            if before_replace is not None:
                before_replace()
            parent.rename(moved_parent)
            parent.symlink_to(redirect, target_is_directory=True)

        return original_replace_in(self, parent_fd, leaf, body, before_replace=rebind)

    monkeypatch.setattr(PosixFiles, "_replace_in", move_after_admission)

    outcome = NativeArtifactWriter().write(
        str(parent / "report.json"), b"anchored bytes", display_is_safe=lambda _value: True
    )

    _successful(outcome)
    assert (moved_parent / "report.json").read_bytes() == b"anchored bytes"
    assert not (redirect / "report.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="Uses POSIX directory descriptors.")
def test_project_protection_guard_rebinding_keeps_protected_bytes(tmp_path, monkeypatch):
    project = tmp_path / "project"
    moved_project = tmp_path / "moved-project"
    redirect = tmp_path / "redirect-project"
    (project / "reports").mkdir(parents=True)
    (project / "source").mkdir()
    (project / "source" / "record.json").write_bytes(b"protected bytes")
    redirect.mkdir()
    original_replace_in = PosixFiles._replace_in

    def move_after_admission(self, parent_fd, leaf, body, *, before_replace=None):
        def rebind() -> None:
            if before_replace is not None:
                before_replace()
            project.rename(moved_project)
            project.symlink_to(redirect, target_is_directory=True)

        return original_replace_in(self, parent_fd, leaf, body, before_replace=rebind)

    monkeypatch.setattr(PosixFiles, "_replace_in", move_after_admission)

    outcome = NativeArtifactWriter((project,)).write(
        str(project / "reports" / "report.json"),
        b"report bytes",
        display_is_safe=lambda _value: True,
    )

    _successful(outcome)
    assert (moved_project / "reports" / "report.json").read_bytes() == b"report bytes"
    assert (moved_project / "source" / "record.json").read_bytes() == b"protected bytes"
    assert not (redirect / "reports" / "report.json").exists()
    assert not (redirect / "source" / "record.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="Injects a POSIX parent fsync failure.")
def test_parent_flush_failure_after_rename_keeps_success_and_new_bytes(tmp_path, monkeypatch):
    destination = tmp_path / "report.bin"
    destination.write_bytes(b"old bytes")
    original_fsync = os.fsync

    def fail_directory_fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("private filesystem detail")
        original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    outcome = NativeArtifactWriter().write(str(destination), b"committed bytes")

    _successful(outcome)
    assert outcome.durability_warning is not None
    assert outcome.durability_warning.reason == "export_durability_unverified"
    assert destination.read_bytes() == b"committed bytes"


@pytest.mark.skipif(os.name != "posix", reason="Injects a POSIX post-commit close failure.")
def test_close_failure_after_rename_keeps_success_and_new_bytes(tmp_path, monkeypatch):
    destination = tmp_path / "report.bin"
    destination.write_bytes(b"old bytes")
    original_open = os.open
    original_close = os.close
    owned_file_fds: set[int] = set()
    injected = False

    def capture_temporary(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if flags & os.O_CREAT:
            owned_file_fds.add(fd)
        return fd

    def fail_owned_close(fd):
        nonlocal injected
        if fd in owned_file_fds and not injected:
            injected = True
            original_close(fd)
            raise OSError("private close detail")
        original_close(fd)

    monkeypatch.setattr(os, "open", capture_temporary)
    monkeypatch.setattr(os, "close", fail_owned_close)
    outcome = NativeArtifactWriter().write(str(destination), b"committed bytes")

    _successful(outcome)
    assert injected
    assert outcome.durability_warning is not None
    assert outcome.durability_warning.reason == "export_durability_unverified"
    assert destination.read_bytes() == b"committed bytes"


@pytest.mark.skipif(os.name != "posix", reason="Injects a POSIX replacement failure.")
def test_replace_failure_preserves_old_bytes_and_cleans_owned_temporary(tmp_path, monkeypatch):
    destination = tmp_path / "report.bin"
    destination.write_bytes(b"old bytes")
    original_replace = os.replace

    def fail_replace(*args, **kwargs):
        raise OSError("private replace detail")

    monkeypatch.setattr(os, "replace", fail_replace)
    outcome = NativeArtifactWriter().write(str(destination), b"new bytes")
    monkeypatch.setattr(os, "replace", original_replace)

    _failed(outcome)
    assert destination.read_bytes() == b"old bytes"
    assert tuple(tmp_path.iterdir()) == (destination,)


@pytest.mark.skipif(os.name != "posix", reason="Injects POSIX file staging faults.")
@pytest.mark.parametrize("fault", ["short_write", "file_fsync"])
def test_staging_faults_preserve_old_bytes_and_remove_temporary(tmp_path, monkeypatch, fault):
    destination = tmp_path / "report.bin"
    destination.write_bytes(b"old bytes")
    if fault == "short_write":
        original_fdopen = os.fdopen

        class ShortWriter:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def write(self, body):
                self.stream.write(body[:-1])
                return len(body) - 1

            def flush(self):
                self.stream.flush()

        monkeypatch.setattr(
            os, "fdopen", lambda *args, **kwargs: ShortWriter(original_fdopen(*args, **kwargs))
        )
    else:
        original_fsync = os.fsync

        def fail_file_fsync(fd):
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("private file flush detail")
            original_fsync(fd)

        monkeypatch.setattr(os, "fsync", fail_file_fsync)

    outcome = NativeArtifactWriter().write(str(destination), b"new bytes")

    _failed(outcome)
    assert destination.read_bytes() == b"old bytes"
    assert tuple(tmp_path.iterdir()) == (destination,)


def test_requested_and_canonical_display_checks_run_before_staging(tmp_path):
    relative = "report.bin"
    calls: list[str] = []
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        outcome = NativeArtifactWriter().write(
            relative,
            b"content",
            display_is_safe=lambda value: calls.append(value) is None and value == relative,
        )
    finally:
        os.chdir(cwd)

    _failed(outcome)
    assert relative in calls
    assert str(tmp_path / relative) in calls
    assert not (tmp_path / relative).exists()
    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.skipif(os.name != "posix", reason="Uses process-relative POSIX destinations.")
def test_final_requested_display_rejection_preserves_old_bytes_and_cleans_temporary(
    tmp_path, monkeypatch
):
    parent = tmp_path / "relative"
    parent.mkdir()
    destination = parent / "report.bin"
    destination.write_bytes(b"old bytes")
    requested = "relative/report.bin"
    requested_checks = 0

    def policy(value: str) -> bool:
        nonlocal requested_checks
        if value == requested:
            requested_checks += 1
            return requested_checks < 3
        return True

    monkeypatch.chdir(tmp_path)
    outcome = NativeArtifactWriter().write(requested, b"new bytes", display_is_safe=policy)

    _failed(outcome)
    assert outcome.error.reason == "unsafe_destination_display"
    assert requested_checks == 3
    assert destination.read_bytes() == b"old bytes"
    assert tuple(parent.iterdir()) == (destination,)


def test_requested_display_rejection_and_callback_exception_fail_before_mutation(tmp_path):
    for predicate in (
        lambda _value: False,
        lambda _value: (_ for _ in ()).throw(RuntimeError("private detail")),
    ):
        destination = tmp_path / f"rejected-{len(tuple(tmp_path.iterdir()))}.bin"
        outcome = NativeArtifactWriter().write(
            str(destination), b"content", display_is_safe=predicate
        )
        _failed(outcome)
        assert outcome.error.reason == "unsafe_destination_display"
        assert not destination.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_display_predicates_are_per_call_under_bounded_concurrency(tmp_path):
    writer = NativeArtifactWriter()
    first_destination = tmp_path / "first.bin"
    second_destination = tmp_path / "second.bin"
    first_entered = threading.Event()
    release_first = threading.Event()
    first_calls = 0
    first_result: list[ArtifactWriteOutcome] = []

    def first_policy(_display: str) -> bool:
        nonlocal first_calls
        first_calls += 1
        if first_calls == 1:
            first_entered.set()
            assert release_first.wait(timeout=5)
            return True
        return False

    thread = threading.Thread(
        target=lambda: first_result.append(
            writer.write(str(first_destination), b"first", display_is_safe=first_policy)
        )
    )
    thread.start()
    assert first_entered.wait(timeout=5)
    second = writer.write(str(second_destination), b"second", display_is_safe=lambda _value: True)
    release_first.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(first_result) == 1
    _failed(first_result[0])
    _successful(second)
    assert not first_destination.exists()
    assert second_destination.read_bytes() == b"second"


def test_outcome_contract_rejects_failed_destination_and_post_failure_warning():
    safe_error = ServiceError(code="internal_error", reason="export_write_failed")
    result = ArtifactWriteOutcome(success=False, destination=None, error=safe_error)
    assert set(result.model_dump(mode="json")) == {
        "success",
        "destination",
        "error",
        "durability_warning",
    }
    with pytest.raises(ValueError):
        ArtifactWriteOutcome(success=False, destination="/private/path", error=safe_error)
    with pytest.raises(ValueError):
        ArtifactWriteOutcome(
            success=False,
            destination=None,
            error=safe_error,
            durability_warning=safe_error,
        )
