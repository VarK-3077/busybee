"""A per-event-loop semaphore bounding concurrent extract windows (global limiter also applies)."""

import asyncio
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[int, asyncio.Semaphore]] = (
    weakref.WeakKeyDictionary()
)


@asynccontextmanager
async def extract_slot(limit: int) -> AsyncIterator[None]:
    """Hold one of `limit` extract slots for the duration of the context."""
    loop = asyncio.get_running_loop()
    entry = _slots.get(loop)
    if entry is None or entry[0] != limit:
        entry = (limit, asyncio.Semaphore(max(1, limit)))
        _slots[loop] = entry
    async with entry[1]:
        yield
