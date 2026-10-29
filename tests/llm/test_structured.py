"""Tests for tolerant JSON extraction, validation, retries, and final failure."""

import pytest
from pydantic import BaseModel

from busybee.llm.messages import Message, Role
from busybee.llm.mock import MockProvider
from busybee.llm.structured import StructuredOutputError, complete_as, extract_json_value


class Reply(BaseModel):
    answer: int


def prompt() -> list[Message]:
    return [Message(role=Role.user, content="What is two plus two?")]


def test_extract_json_value_accepts_code_fences() -> None:
    assert extract_json_value('```json\n{"answer": 4}\n```') == {"answer": 4}


def test_extract_json_value_accepts_prose_before_and_after() -> None:
    text = 'Here is the result: {"answer": 5} I hope that helps.'
    assert extract_json_value(text) == {"answer": 5}


async def test_complete_as_parses_fenced_json() -> None:
    provider = MockProvider({"math": ['```json\n{"answer": 4}\n```']})

    reply = await complete_as(provider, prompt(), Reply, task="math")

    assert reply.answer == 4
    assert provider.calls[0].json_schema is not None
    assert "confidence" not in provider.calls[0].json_schema["properties"]


async def test_complete_as_parses_prose_and_json() -> None:
    provider = MockProvider({"math": ['The answer is {"answer": 5}.']})

    reply = await complete_as(provider, prompt(), Reply, task="math")

    assert reply.answer == 5


async def test_complete_as_reprompts_with_validation_error() -> None:
    provider = MockProvider({"math": ['{"answer": "not a number"}', '{"answer": 7}']})

    reply = await complete_as(provider, prompt(), Reply, task="math")

    assert reply.answer == 7
    assert len(provider.calls) == 2
    retry_text = provider.calls[1].messages[-1].content
    assert "invalid" in retry_text.lower()
    assert "answer" in retry_text


async def test_complete_as_raises_with_last_text_after_retries() -> None:
    provider = MockProvider({"math": ["not json at all"]})

    with pytest.raises(StructuredOutputError) as captured:
        await complete_as(provider, prompt(), Reply, task="math", retries=1)

    assert captured.value.last_text == "not json at all"
    assert captured.value.text == "not json at all"
    assert captured.value.attempts == 2
    assert len(provider.calls) == 2
