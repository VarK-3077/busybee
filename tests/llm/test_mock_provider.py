"""Tests for fixture ordering, callable responses, and fixture loading."""

import json
from pathlib import Path

from busybee.llm.messages import Message, Role
from busybee.llm.mock import MockProvider, load_fixtures


def message(text: str) -> Message:
    return Message(role=Role.user, content=text)


async def test_fixture_responses_are_consumed_in_order_and_last_repeats() -> None:
    provider = MockProvider({"extract": ["first", "second"]})

    replies = [
        (await provider.complete([message("one")], task="extract")).text,
        (await provider.complete([message("two")], task="extract")).text,
        (await provider.complete([message("three")], task="extract")).text,
    ]

    assert replies == ["first", "second", "second"]
    assert len(provider.calls) == 3
    assert provider.calls[0]["task"] == "extract"
    assert provider.calls[0].messages[0].content == "one"


async def test_callable_receives_messages_and_task() -> None:
    def responder(messages: list[Message], task: str) -> str:
        return f"{task}:{messages[-1].content}"

    provider = MockProvider(responder)
    completion = await provider.complete([message("payload")], task="verify")

    assert completion.text == "verify:payload"
    assert completion.model == "mock"
    assert provider.calls[0].task == "verify"


async def test_async_callable_is_supported() -> None:
    async def responder(messages: list[Message], task: str) -> str:
        return f"{task}-{len(messages)}"

    provider = MockProvider(responder)
    completion = await provider.complete([message("a"), message("b")], task="infer")

    assert completion.text == "infer-2"


def test_load_fixtures_reads_recording_records(tmp_path: Path) -> None:
    records = [
        {"task": "extract", "messages": [], "text": "alpha"},
        {"task": "extract", "messages": [], "text": "beta"},
    ]
    (tmp_path / "extract.json").write_text(json.dumps(records), encoding="utf-8")
    (tmp_path / "missing.json").unlink(missing_ok=True)

    fixtures = load_fixtures(tmp_path)

    assert fixtures == {"extract": ["alpha", "beta"]}
    assert MockProvider.load_fixtures(tmp_path) == fixtures
