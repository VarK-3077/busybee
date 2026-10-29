"""Append-only JSONL audit log for every provider attempt, serialised by a lock."""

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .messages import Message, Usage

_path: Path | None = None
_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None


class AuditEntry(BaseModel):
    """One provider attempt as written to the audit log."""

    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    task: str = ""
    model: str = ""
    messages: list[Message] = Field(default_factory=list)
    text: str = ""
    usage: Usage = Field(default_factory=Usage)
    latency_s: float = 0.0
    attempt: int = 1
    finish_reason: str | None = None


def configure(path: str | Path | None) -> None:
    """Point the audit log at a file, or disable it with None."""
    global _path, _lock, _lock_loop
    _path = Path(path) if path is not None else None
    _lock = None
    _lock_loop = None


def _jsonable(entry: AuditEntry | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(entry, BaseModel):
        return entry.model_dump(mode="json")
    data = dict(entry)
    data.setdefault("ts", datetime.now(UTC).isoformat())
    messages = data.get("messages")
    if isinstance(messages, list):
        data["messages"] = [
            message.model_dump(mode="json")
            if isinstance(message, BaseModel)
            else dict(message)
            if isinstance(message, Mapping)
            else message
            for message in messages
        ]
    usage = data.get("usage")
    if isinstance(usage, BaseModel):
        data["usage"] = usage.model_dump(mode="json")
    return data


def _current_lock() -> asyncio.Lock:
    global _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop is not loop:
        _lock = asyncio.Lock()
        _lock_loop = loop
    return _lock


def _write_line(target: Path, line: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


async def record(entry: AuditEntry | Mapping[str, Any]) -> None:
    """Append one audit entry, doing nothing when no path has been configured."""
    target = _path
    if target is None:
        return
    line = json.dumps(_jsonable(entry), ensure_ascii=False)
    async with _current_lock():
        await asyncio.to_thread(_write_line, target, line)
