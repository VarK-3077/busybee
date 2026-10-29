"""Tests for forwarding through RecordingProvider and replaying its fixtures."""

import json
from pathlib import Path

from busybee.llm.messages import Message, Role
from busybee.llm.mock import MockProvider, load_fixtures
from busybee.llm.recording import RecordingProvider


def prompt(text: str) -> list[Message]:
    return [Message(role=Role.user, content=text)]


async def test_recording_forwards_and_saves_first_reply(tmp_path: Path) -> None:
    inner = MockProvider({"extract": ["alpha"]})
    provider = RecordingProvider(inner, tmp_path)

    completion = await provider.complete(prompt("page text"), task="extract")

    path = tmp_path / "extract.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert completion.text == "alpha"
    assert provider.name == "mock"
    assert saved == {
        "task": "extract",
        "messages": [{"role": "user", "content": "page text"}],
        "text": "alpha",
    }


async def test_recording_appends_multiple_replies(tmp_path: Path) -> None:
    inner = MockProvider({"extract": ["alpha", "beta"]})
    provider = RecordingProvider(inner, tmp_path)

    await provider.complete(prompt("one"), task="extract")
    await provider.complete(prompt("two"), task="extract")

    saved = json.loads((tmp_path / "extract.json").read_text(encoding="utf-8"))
    assert [record["text"] for record in saved] == ["alpha", "beta"]
    assert load_fixtures(tmp_path) == {"extract": ["alpha", "beta"]}
