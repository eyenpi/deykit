"""FIFO API source admission does not change default native-lock conflicts."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from deykit.application.errors import ServiceFailure
from deykit.storage.source import FileProjectSource


def _wait_for_waiters(source: FileProjectSource, count: int) -> None:
    deadline = time.monotonic() + 2
    with source._admission_condition:
        while len(source._admission_waiters) < count:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "admission waiter did not queue"
            source._admission_condition.wait(remaining)


def _thread_call(
    name: str, source: FileProjectSource, errors: list[BaseException]
) -> Callable[[], None]:
    def call() -> None:
        try:
            source.capture_snapshot()
        except BaseException as error:
            errors.append(error)

    return call


def test_api_admission_preserves_fifo_order_across_complete_read_epochs(tmp_path):
    first_entered = threading.Event()
    release_first = threading.Event()
    entered_names: list[str] = []
    seen: set[str] = set()
    seen_lock = threading.Lock()

    def hook(stage: str) -> None:
        if stage != "snapshot_captured":
            return
        name = threading.current_thread().name
        with seen_lock:
            if name in seen:
                return
            seen.add(name)
            entered_names.append(name)
        if name == "first":
            first_entered.set()
            assert release_first.wait(2), "first source epoch was not released"

    with FileProjectSource(
        tmp_path / "fifo",
        create=True,
        fault_hook=hook,
        admission_timeout_seconds=2,
    ) as source:
        errors: list[BaseException] = []
        threads = [
            threading.Thread(target=_thread_call(name, source, errors), name=name)
            for name in ("first", "second", "third")
        ]
        threads[0].start()
        assert first_entered.wait(2), "first source epoch did not start"
        threads[1].start()
        _wait_for_waiters(source, 2)
        threads[2].start()
        _wait_for_waiters(source, 3)
        release_first.set()
        for thread in threads:
            thread.join(3)
            assert not thread.is_alive(), "source admission thread did not settle"

    assert errors == []
    assert entered_names == ["first", "second", "third"]


def test_admission_timeout_removes_ticket_and_next_waiter_can_enter(tmp_path):
    first_entered = threading.Event()
    release_first = threading.Event()
    entered_names: list[str] = []
    errors: dict[str, BaseException] = {}
    expired_finished = threading.Event()
    lock = threading.Lock()

    def hook(stage: str) -> None:
        if stage != "snapshot_captured":
            return
        name = threading.current_thread().name
        with lock:
            if name in entered_names:
                return
            entered_names.append(name)
        if name == "holder":
            first_entered.set()
            assert release_first.wait(2), "holder source epoch was not released"

    def call(source: FileProjectSource, name: str) -> None:
        try:
            source.capture_snapshot()
        except BaseException as error:
            errors[name] = error
        finally:
            if name == "expired":
                expired_finished.set()

    with FileProjectSource(
        tmp_path / "timeout",
        create=True,
        fault_hook=hook,
        admission_timeout_seconds=1,
    ) as source:
        holder = threading.Thread(target=call, args=(source, "holder"), name="holder")
        expired = threading.Thread(target=call, args=(source, "expired"), name="expired")
        following = threading.Thread(target=call, args=(source, "following"), name="following")
        holder.start()
        assert first_entered.wait(2)
        expired.start()
        _wait_for_waiters(source, 2)
        assert expired_finished.wait(2), "oldest ticket did not expire"
        with source._admission_condition:
            assert len(source._admission_waiters) == 1
        following.start()
        _wait_for_waiters(source, 2)
        release_first.set()
        for thread in (holder, expired, following):
            thread.join(3)
            assert not thread.is_alive(), "source admission thread did not settle"

    assert isinstance(errors.get("expired"), ServiceFailure)
    assert errors["expired"].error.code == "conflict"
    assert errors["expired"].error.reason == "source_busy"
    assert "following" not in errors
    assert entered_names == ["holder", "following"]


def test_default_admission_still_reports_independent_native_lock_conflict(tmp_path):
    with (
        FileProjectSource(tmp_path / "native", create=True) as first,
        FileProjectSource(tmp_path / "native") as second,
    ):
        with first.consistent_read():
            with pytest.raises(ServiceFailure) as failure:
                second.capture_snapshot()

    assert failure.value.error.code == "conflict"
    assert failure.value.error.reason == "source_busy"


def test_invalid_admission_timeout_is_rejected_before_source_creation(tmp_path):
    path = tmp_path / "invalid-timeout"
    with pytest.raises(ValueError, match="invalid_source_admission_timeout"):
        FileProjectSource(path, create=True, admission_timeout_seconds=-1)
    assert not path.exists()


def test_nested_reads_remain_reentrant_with_api_admission_enabled(tmp_path):
    with FileProjectSource(
        tmp_path / "nested",
        create=True,
        admission_timeout_seconds=1,
    ) as source:
        with source.consistent_read():
            with source.consistent_read():
                assert source.capture_snapshot() == ()
        assert source.capture_snapshot() == ()


def test_nested_read_bypasses_queued_ticket_inside_existing_epoch(tmp_path):
    nested_requested = threading.Event()
    nested_finished = threading.Event()
    release_holder = threading.Event()
    second_entered = threading.Event()
    entered: list[str] = []
    entered_lock = threading.Lock()
    source_ref: list[FileProjectSource] = []
    nested_once = False

    def hook(stage: str) -> None:
        nonlocal nested_once
        if stage != "snapshot_captured":
            return
        name = threading.current_thread().name
        with entered_lock:
            if name not in entered:
                entered.append(name)
        if name == "holder" and not nested_once:
            nested_once = True
            assert nested_requested.wait(2), "queued read did not trigger nested read"
            source_ref[0].capture_snapshot()
            nested_finished.set()
            assert release_holder.wait(2), "holder source epoch was not released"
        elif name == "second":
            second_entered.set()

    def capture(source: FileProjectSource) -> None:
        source.capture_snapshot()

    with FileProjectSource(
        tmp_path / "nested-queued",
        create=True,
        fault_hook=hook,
        admission_timeout_seconds=2,
    ) as source:
        source_ref.append(source)
        holder = threading.Thread(target=capture, args=(source,), name="holder")
        second = threading.Thread(target=capture, args=(source,), name="second")
        holder.start()
        _wait_for_waiters(source, 1)
        second.start()
        _wait_for_waiters(source, 2)
        nested_requested.set()
        assert nested_finished.wait(2), "nested read waited behind a queued ticket"
        assert not second_entered.is_set()
        release_holder.set()
        holder.join(3)
        second.join(3)
        assert not holder.is_alive() and not second.is_alive()

    assert entered == ["holder", "second"]


def test_exception_in_admitted_epoch_releases_fifo_ticket_for_next_waiter(tmp_path):
    holder_entered = threading.Event()
    release_holder = threading.Event()
    entered: list[str] = []
    entered_lock = threading.Lock()
    errors: dict[str, BaseException] = {}

    def hook(stage: str) -> None:
        if stage != "snapshot_captured":
            return
        name = threading.current_thread().name
        with entered_lock:
            if name in entered:
                return
            entered.append(name)
        if name == "holder":
            holder_entered.set()
            assert release_holder.wait(2), "holder source epoch was not released"
        elif name == "failing":
            raise RuntimeError("fixture_fault")

    def call(source: FileProjectSource, name: str) -> None:
        try:
            source.capture_snapshot()
        except BaseException as error:
            errors[name] = error

    with FileProjectSource(
        tmp_path / "exception",
        create=True,
        fault_hook=hook,
        admission_timeout_seconds=2,
    ) as source:
        holder = threading.Thread(target=call, args=(source, "holder"), name="holder")
        failing = threading.Thread(target=call, args=(source, "failing"), name="failing")
        following = threading.Thread(target=call, args=(source, "following"), name="following")
        holder.start()
        assert holder_entered.wait(2), "holder source epoch did not start"
        failing.start()
        _wait_for_waiters(source, 2)
        following.start()
        _wait_for_waiters(source, 3)
        release_holder.set()
        for thread in (holder, failing, following):
            thread.join(3)
            assert not thread.is_alive(), "source admission thread did not settle"

    assert isinstance(errors.get("failing"), RuntimeError)
    assert "following" not in errors
    assert entered == ["holder", "failing", "following"]
