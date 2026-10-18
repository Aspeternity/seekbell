"""Keep short storage operations inside the lifetime of the process lock."""

import asyncio
from collections.abc import Callable
from contextlib import suppress


async def storage_call[T](function: Callable[..., T], *args, **kwargs) -> T:
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancellation cannot stop a SQLite thread. Drain it before releasing the data lock.
        with suppress(Exception):
            await task
        raise


async def wait_for_signal(stop: asyncio.Event, wake: asyncio.Event | None, delay: float) -> None:
    waits = [asyncio.create_task(stop.wait())]
    if wake is not None:
        waits.append(asyncio.create_task(wake.wait()))
    try:
        await asyncio.wait(waits, timeout=max(0, delay), return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in waits:
            task.cancel()
        await asyncio.gather(*waits, return_exceptions=True)
