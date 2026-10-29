"""One global asyncio semaphore that every provider call passes through."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_concurrency: int | None = None
_semaphore: asyncio.Semaphore | None = None
_loop: asyncio.AbstractEventLoop | None = None


def configure(concurrency: int) -> None:
    """Set the maximum number of simultaneous provider calls."""
    global _concurrency, _semaphore, _loop
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    _concurrency = concurrency
    _semaphore = asyncio.Semaphore(concurrency)
    _loop = None


def _current() -> asyncio.Semaphore | None:
    global _semaphore, _loop
    if _concurrency is None:
        return None
    loop = asyncio.get_running_loop()
    if _semaphore is None or _loop is not loop:
        _semaphore = asyncio.Semaphore(_concurrency)
        _loop = loop
    return _semaphore


@asynccontextmanager
async def limited() -> AsyncIterator[None]:
    """Hold the global provider slot for the duration of the context."""
    semaphore = _current()
    if semaphore is None:
        yield
        return
    async with semaphore:
        yield
