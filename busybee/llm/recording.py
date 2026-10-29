"""Provider wrapper that saves real replies as replayable mock fixtures."""

import asyncio
import re
from pathlib import Path
from typing import Any

from busybee.schema.io import read_json, write_json_atomic

from .messages import Completion, Message
from .provider import Provider


def _fixture_path(directory: Path, task: str) -> Path:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", task).strip("_") or "untitled"
    return directory / f"{stem}.json"


def _read_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


class RecordingProvider:
    """Forward calls to a real provider while recording each reply to disk."""

    def __init__(
        self,
        inner: Provider,
        directory: str | Path | None = None,
        *,
        dir: str | Path | None = None,
    ) -> None:
        target = directory if directory is not None else dir
        if target is None:
            raise TypeError("RecordingProvider needs a fixture directory")
        self._inner = inner
        self._directory = Path(target)
        self._lock = asyncio.Lock()
        self.name = inner.name
        self.model = inner.model

    async def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: str = "",
        timeout_s: float | None = None,
    ) -> Completion:
        """Forward one call and append its reply to the task fixture file."""
        extra = {} if timeout_s is None else {"timeout_s": timeout_s}
        completion = await self._inner.complete(
            messages,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            task=task,
            **extra,
        )
        record = {
            "task": task,
            "messages": [message.model_dump(mode="json") for message in messages],
            "text": completion.text,
        }
        async with self._lock:
            path = _fixture_path(self._directory, task)
            records = _read_existing(path)
            records.append(record)
            payload: Any = records[0] if len(records) == 1 else records
            write_json_atomic(path, payload)
        return completion
