"""Server-local clock and identity adapters."""

import asyncio
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import Executor
from datetime import UTC, datetime
from time import monotonic
from typing import Any, TypeVar
from uuid import uuid4


class SystemClock:
    def utc_now(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def monotonic(self) -> float:
        return monotonic()


def new_id() -> str:
    return uuid4().hex


R = TypeVar("R")


class _OwnedLoopCancellation:
    """Publish cancellation even when it races worker-loop startup."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[Any] | None = None
        self._requested = False

    def bind(self, loop: asyncio.AbstractEventLoop, task: asyncio.Task[Any]) -> bool:
        with self._lock:
            self._loop = loop
            self._task = task
            return self._requested

    def unbind(self, loop: asyncio.AbstractEventLoop, task: asyncio.Task[Any]) -> None:
        with self._lock:
            if self._loop is loop and self._task is task:
                self._loop = None
                self._task = None

    def request(self) -> None:
        with self._lock:
            if self._requested:
                return
            self._requested = True
            loop, task = self._loop, self._task
            if loop is not None and task is not None:
                loop.call_soon_threadsafe(task.cancel)


class TrackedWorkers:
    """Strongly retain admitted synchronous work until it settles at shutdown."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Future[Any]] = set()

    async def run_sync(self, function: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._discard)
        return await asyncio.shield(task)

    async def run_async(
        self,
        function: Callable[..., Coroutine[Any, Any, R]],
        *args: Any,
        **kwargs: Any,
    ) -> R:
        task = asyncio.create_task(function(*args, **kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._discard)
        return await asyncio.shield(task)

    async def run_owned_async(
        self,
        factory: Callable[[], Coroutine[Any, Any, R]],
        *,
        executor: Executor | None = None,
    ) -> R:
        """Run one complete coroutine on an owned thread and join on cancellation."""
        cancellation = _OwnedLoopCancellation()

        def run() -> R:
            async def owned() -> R:
                task = asyncio.current_task()
                if task is None:
                    raise RuntimeError("owned_task_missing")
                loop = asyncio.get_running_loop()
                already_requested = cancellation.bind(loop, task)
                try:
                    if already_requested:
                        raise asyncio.CancelledError()
                    return await factory()
                finally:
                    cancellation.unbind(loop, task)

            return asyncio.run(owned())

        worker = asyncio.get_running_loop().run_in_executor(executor, run)
        self._tasks.add(worker)
        worker.add_done_callback(self._discard)
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancellation.request()
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    if worker.done():
                        break
                    cancellation.request()
                except BaseException:
                    break
            raise

    def _discard(self, task: asyncio.Future[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    async def wait_idle(self) -> None:
        while self._tasks:
            tasks = tuple(self._tasks)
            if all(task.done() for task in tasks):
                await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
            else:
                await asyncio.gather(*tasks, return_exceptions=True)
