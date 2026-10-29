"""The audit log lock and the limiter must survive several `asyncio.run` calls in one process."""

import asyncio
from pathlib import Path

from busybee.llm import audit_log, limiter


async def _record_and_limit(count: int) -> None:
    async def one(index: int) -> None:
        async with limiter.limited():
            await audit_log.record({"task": f"t{index}"})

    await asyncio.gather(*(one(i) for i in range(count)))


def test_two_event_loops_share_audit_log_and_limiter(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    audit_log.configure(path)
    limiter.configure(2)
    try:
        asyncio.run(_record_and_limit(5))
        asyncio.run(_record_and_limit(5))
    finally:
        audit_log.configure(None)
        limiter._concurrency = None
    assert len(path.read_text(encoding="utf-8").splitlines()) == 10
