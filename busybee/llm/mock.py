"""Deterministic mock provider driven by fixtures or a callable, and its loader."""

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .messages import Completion, Message, Usage
from .provider import complete_and_record
from .tokens import count_tokens


class CallRecord(dict[str, Any]):
    """One recorded call, readable as a mapping or through attributes."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error


def _texts_from(payload: Any) -> list[str]:
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, list):
        texts: list[str] = []
        for item in payload:
            texts.extend(_texts_from(item))
        return texts
    if isinstance(payload, dict):
        for key in ("text", "response", "content"):
            if key in payload:
                return _texts_from(payload[key])
        for key in ("responses", "texts"):
            if key in payload:
                return _texts_from(payload[key])
    return []


def load_fixtures(directory: str | Path) -> dict[str, list[str]]:
    """Read every <task>.json fixture file into an ordered task-to-texts mapping."""
    root = Path(directory)
    fixtures: dict[str, list[str]] = {}
    if not root.exists():
        return fixtures
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixtures.setdefault(path.stem, []).extend(_texts_from(payload))
    return fixtures


class MockProvider:
    """A provider that replays fixture texts or delegates to a callable."""

    def __init__(
        self,
        responses: dict[str, list[str]] | str | Callable[[list[Message], str], str] | None = None,
        *,
        model: str = "mock",
        name: str = "mock",
        default_response: str = "",
    ) -> None:
        self.name = name
        self.model = model
        self.responses = responses
        self.default_response = default_response
        self.calls: list[CallRecord] = []
        self._indices: dict[str, int] = {}

    @classmethod
    def load_fixtures(cls, directory: str | Path) -> dict[str, list[str]]:
        """Read fixture files for use as the responses mapping."""
        return load_fixtures(directory)

    @classmethod
    def from_fixtures(cls, directory: str | Path, **kwargs: Any) -> "MockProvider":
        """Build a provider whose responses come from a fixture directory."""
        return cls(load_fixtures(directory), **kwargs)

    async def _next_text(self, messages: list[Message], task: str) -> str:
        responses = self.responses
        if responses is None:
            return self.default_response
        if isinstance(responses, str):
            return responses
        if callable(responses):
            result = responses(messages, task)
            if inspect.isawaitable(result):
                result = await result
            return str(result)
        texts = responses.get(task)
        if texts is None:
            if "*" in responses:
                texts = responses["*"]
            elif "default" in responses:
                texts = responses["default"]
            else:
                return self.default_response
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return self.default_response
        index = self._indices.get(task, 0)
        self._indices[task] = index + 1
        return texts[min(index, len(texts) - 1)]

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
        """Return the next fixture response for the task and record the call."""
        self.calls.append(
            CallRecord(
                messages=messages,
                task=task,
                json_schema=json_schema,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        async def call() -> tuple[str, Usage]:
            text = await self._next_text(messages, task)
            prompt = "\n".join(message.content for message in messages)
            return text, Usage(
                input_tokens=count_tokens(prompt),
                output_tokens=count_tokens(text),
            )

        return await complete_and_record(
            model=self.model,
            messages=messages,
            task=task,
            attempt=1,
            request=call,
        )
