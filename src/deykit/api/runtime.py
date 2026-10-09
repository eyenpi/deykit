"""Server-local clock and identity adapters."""

import asyncio
from collections.abc import Awaitable, Callable
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


class TrackedWorkers:
    """Strongly retain admitted synchronous work until it settles at shutdown."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    async def run_sync(self, function: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._discard)
        return await asyncio.shield(task)

    async def run_async(
        self, function: Callable[..., Awaitable[R]], *args: Any, **kwargs: Any
    ) -> R:
        task = asyncio.create_task(function(*args, **kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._discard)
        return await asyncio.shield(task)

    def _discard(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
