"""Path demo acquisition refuses unrelated trees before any source mutation."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from deykit.application.demo import DemoService
from deykit.application.demo import ExistingDemoDestination
from deykit.application.errors import ServiceFailure
from deykit.contracts.ports import CommitReceipt
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


class Clock:
    def utc_now(self) -> str:
        return "2026-10-09T12:00:00Z"

    def monotonic(self) -> float:
        return 0.0


def _tree(root: Path) -> tuple[tuple[str, str, bytes | None], ...]:
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append((relative, "symlink", path.readlink().as_posix().encode()))
        elif path.is_dir():
            entries.append((relative, "directory", None))
        else:
            entries.append((relative, "file", path.read_bytes()))
    return tuple(entries)


@pytest.mark.parametrize("contents", ["empty", "nested", "metadata"])
def test_existing_unrelated_demo_destination_is_recursively_unchanged(
    tmp_path, contents, monkeypatch
):
    root = tmp_path / "selected"
    root.mkdir()
    if contents == "nested":
        (root / "notes").mkdir()
        (root / "notes" / "user.txt").write_bytes(b"keep these exact bytes\x00\xff")
    elif contents == "metadata":
        (root / ".deykit").mkdir()
        (root / ".deykit" / "user-owned").write_text("keep")
    before = _tree(root)
    staged = []

    def forbidden_staging():
        staged.append(True)
        raise AssertionError("unrelated destination reached staging")

    class ForbiddenClock:
        def utc_now(self):
            raise AssertionError("unrelated destination consulted the clock")

        def monotonic(self):
            raise AssertionError("unrelated destination consulted monotonic time")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unrelated destination consulted corpus or IDs")

    monkeypatch.setattr("deykit.application.demo.read_sandbox_corpus", forbidden)

    service = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        ForbiddenClock(),
        forbidden,
        staging_factory=forbidden_staging,
        destination_factory=FileDemoDestinationFactory(),
    )
    with pytest.raises(ServiceFailure) as failure:
        service.create(root, operation_id="refuse-user-folder")
    assert (failure.value.error.code, failure.value.error.reason) == (
        "conflict",
        "demo_path_exists",
    )
    assert _tree(root) == before
    assert staged == []


def test_unrelated_valid_project_is_not_adopted_or_mutated(tmp_path):
    root = tmp_path / "valid-project"
    root.mkdir()
    with FileProjectSource(root, create=True) as source:
        from deykit.application.projects import ProjectService

        ProjectService(
            lambda path, create: FileProjectSource(path, create=create),
            Clock(),
            lambda: "unused-id",
        ).create_in(source, "Existing project", "existing-project")
    before = _tree(root)
    service = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        Clock(),
        staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
    )
    with pytest.raises(ServiceFailure) as failure:
        service.create(root, operation_id="attempt-demo")
    assert failure.value.error.reason == "demo_path_exists"
    assert _tree(root) == before


def test_existing_receipt_with_different_intent_keeps_namespace_conflict(tmp_path, monkeypatch):
    root = tmp_path / "existing-demo"
    service = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        Clock(),
        staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
    )
    created = service.create(root, operation_id="namespace-operation")
    before = _tree(root)
    monkeypatch.setattr("deykit.application.demo.DEMO_OPERATION_INTENT", "0" * 64)
    with pytest.raises(ServiceFailure) as failure:
        service.create(root, operation_id=created.operation_id)
    assert failure.value.error.reason == "operation_id_conflict"
    assert _tree(root) == before


def test_failed_readonly_receipt_admission_closes_candidate_once(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    actual = FileProjectSource(root)

    class TrackingSource:
        close_count = 0

        def close(self):
            self.close_count += 1
            actual.close()

    tracked = TrackingSource()

    class ExistingFactory:
        def open_existing(self, path, *, operation_id, intent_hash):
            return ExistingDemoDestination(
                tracked, CommitReceipt("wrong-operation", (), False, ())
            )

        def create_exclusive(self, path):
            raise AssertionError("failed admission reached creation")

    service = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        Clock(),
        staging_factory=DemoStagingSource,
        destination_factory=ExistingFactory(),
    )
    with pytest.raises(ServiceFailure) as failure:
        service.create_opened(root, operation_id="expected-operation")
    assert failure.value.error.reason == "invalid_demo_receipt"
    assert tracked.close_count == 1
    assert not (root / ".deykit").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow final-root oracle")
def test_final_symlink_is_refused_without_touching_target(tmp_path):
    target = tmp_path / "keep"
    target.mkdir()
    (target / "user.txt").write_bytes(b"untouched")
    link = tmp_path / "selected"
    link.symlink_to(target, target_is_directory=True)
    before = _tree(target)
    service = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        Clock(),
        staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
    )
    with pytest.raises(ServiceFailure) as failure:
        service.create(link, operation_id="refuse-symlink")
    assert failure.value.error.reason == "demo_path_exists"
    assert link.is_symlink()
    assert _tree(target) == before


@pytest.mark.parametrize("replacement_phase", ["after_mkdir", "after_open"])
@pytest.mark.skipif(os.name != "posix", reason="POSIX mkdir/open acquisition boundaries")
def test_replaced_acquired_directory_with_sentinel_is_refused_before_source_writes(
    tmp_path, replacement_phase
):
    root = tmp_path / "selected"

    def replace_after_mkdir(phase: str) -> None:
        if phase == replacement_phase:
            root.rmdir()
            root.mkdir()
            (root / "sentinel.txt").write_bytes(b"preserve race loser")

    service = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        Clock(),
        staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(
            acquisition_hook=replace_after_mkdir
        ),
    )
    with pytest.raises(ServiceFailure) as failure:
        service.create(root, operation_id="race-sentinel")
    assert failure.value.error.reason == "demo_path_exists"
    assert _tree(root) == (("sentinel.txt", "file", b"preserve race loser"),)


def test_simultaneous_fresh_path_create_has_one_owner_and_retry_replays(tmp_path):
    root = tmp_path / "contended"
    barrier = Barrier(2)

    class SynchronizedStagingSource(DemoStagingSource):
        def capture_snapshot(self, keys=None):
            records = super().capture_snapshot(keys)
            barrier.wait(timeout=30)
            return records

    def create():
        return DemoService(
            lambda path, create: FileProjectSource(path, create=create),
            Clock(),
            staging_factory=SynchronizedStagingSource,
            destination_factory=FileDemoDestinationFactory(),
        ).create(root, operation_id="same-demo-operation")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(create) for _ in range(2)]
        succeeded = []
        failed = []
        for result in results:
            try:
                succeeded.append(result.result(timeout=60))
            except ServiceFailure as error:
                failed.append(error.error.reason)
    assert len(succeeded) == 1
    assert failed == ["demo_path_exists"]
    replayed = DemoService(
        lambda path, create: FileProjectSource(path, create=create),
        Clock(),
        staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
    ).create(root, operation_id="same-demo-operation")
    assert replayed.replayed is True
    assert replayed.project_id == succeeded[0].project_id
