"""Owned group workers keep their loop, thread, and completion join together."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident

import pytest

from deykit.api.runtime import TrackedWorkers


def test_owned_coroutine_keeps_one_worker_thread_and_loop():
    async def scenario() -> None:
        workers = TrackedWorkers()
        caller_thread = get_ident()
        caller_loop = asyncio.get_running_loop()
        observations: list[tuple[int, asyncio.AbstractEventLoop]] = []

        async def operation() -> str:
            observations.append((get_ident(), asyncio.get_running_loop()))
            await asyncio.sleep(0)
            observations.append((get_ident(), asyncio.get_running_loop()))
            return "settled"

        assert await workers.run_owned_async(operation) == "settled"
        assert len(observations) == 2
        assert observations[0] == observations[1]
        assert observations[0][0] != caller_thread
        assert observations[0][1] is not caller_loop
        await workers.wait_idle()
        assert workers._tasks == set()

    asyncio.run(scenario())


def test_cancel_before_worker_loop_bind_is_published_and_joined():
    async def scenario() -> None:
        executor = ThreadPoolExecutor(max_workers=1)
        blocker_started = Event()
        release_blocker = Event()
        invoked = Event()

        def blocker() -> None:
            blocker_started.set()
            if not release_blocker.wait(2):
                raise AssertionError("executor blocker was not released")

        blocker_future = executor.submit(blocker)
        assert blocker_started.wait(2), "executor blocker did not start"
        workers = TrackedWorkers()
        task: asyncio.Task[None] | None = None

        async def operation() -> None:
            invoked.set()

        try:
            task = asyncio.create_task(workers.run_owned_async(operation, executor=executor))
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), "cancelled caller did not wait for worker settlement"
            release_blocker.set()
            await asyncio.wrap_future(blocker_future)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
            await asyncio.wait_for(workers.wait_idle(), timeout=3)
        finally:
            release_blocker.set()
            if task is not None and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=3)
                except BaseException:
                    pass
            await asyncio.wait_for(asyncio.to_thread(executor.shutdown, wait=True), timeout=3)
        assert not invoked.is_set()

    asyncio.run(scenario())


def test_wait_idle_yields_for_queued_completed_worker_cleanup():
    async def scenario() -> None:
        workers = TrackedWorkers()
        completed = asyncio.get_running_loop().create_future()
        cleanup_ran = asyncio.Event()

        def cleanup(future: asyncio.Future[object]) -> None:
            workers._tasks.discard(future)
            cleanup_ran.set()

        workers._tasks.add(completed)
        completed.add_done_callback(cleanup)
        completed.set_result(None)
        await asyncio.wait_for(workers.wait_idle(), timeout=3)
        assert cleanup_ran.is_set()
        assert workers._tasks == set()

    asyncio.run(scenario())


def test_repeated_caller_cancellation_joins_held_worker_cleanup_once():
    async def scenario() -> None:
        workers = TrackedWorkers()
        operation_started = Event()
        cleanup_started = Event()
        cleanup_released = Event()
        worker_loop: list[asyncio.AbstractEventLoop] = []
        cleanup_count = 0

        async def operation() -> None:
            nonlocal cleanup_count
            worker_loop.append(asyncio.get_running_loop())
            operation_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                if not await asyncio.to_thread(cleanup_released.wait, 5):
                    raise AssertionError("worker cleanup was not released")
                cleanup_count += 1

        caller = asyncio.create_task(workers.run_owned_async(operation))
        assert await asyncio.to_thread(operation_started.wait, 5), "owned operation did not start"
        caller.cancel()
        assert await asyncio.to_thread(cleanup_started.wait, 5), (
            "owned cleanup did not start after cancellation"
        )
        assert workers._tasks

        caller.cancel()
        barrier = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(barrier.set_result, None)
        await barrier
        assert not caller.done(), "caller cancellation bypassed held worker cleanup"
        assert workers._tasks, "worker was untracked before cleanup settled"

        worker_loop[0].call_soon_threadsafe(cleanup_released.set)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(caller, timeout=5)
        await asyncio.wait_for(workers.wait_idle(), timeout=5)
        assert cleanup_count == 1
        assert workers._tasks == set()

    asyncio.run(scenario())


def test_worker_cancelled_error_after_unbind_does_not_escape_as_closed_loop_error():
    async def scenario() -> None:
        workers = TrackedWorkers()

        async def operation() -> None:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(workers.run_owned_async(operation), timeout=5)
        await asyncio.wait_for(workers.wait_idle(), timeout=5)
        assert workers._tasks == set()

    asyncio.run(scenario())
