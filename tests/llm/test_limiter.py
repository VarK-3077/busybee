"""Tests that the global limiter bounds concurrency, including provider calls."""

import asyncio

from busybee.llm.limiter import configure, limited
from busybee.llm.messages import Message, Role
from busybee.llm.mock import MockProvider


async def test_limited_bounds_concurrency() -> None:
    configure(2)
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with limited():
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(worker() for _ in range(8)))

    assert peak == 2


async def test_provider_calls_go_through_the_limiter() -> None:
    configure(1)
    active = 0
    peak = 0

    async def responder(messages: list[Message], task: str) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "{}"

    provider = MockProvider(responder)
    calls = [
        provider.complete([Message(role=Role.user, content=str(index))], task="extract")
        for index in range(4)
    ]
    await asyncio.gather(*calls)

    assert peak == 1
