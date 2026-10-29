"""Tests that the Anthropic provider extracts system turns and parses replies."""

import json
from typing import Any

import httpx

from busybee.llm.anthropic import AnthropicProvider
from busybee.llm.messages import Message, Role


def anthropic_reply(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }


async def test_system_messages_are_moved_out_of_the_chat_list() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=anthropic_reply("hello"))

    provider = AnthropicProvider(
        "claude-test",
        api_key="test",
        base_url="http://test",
        http_client=httpx.MockTransport(handler),
    )

    completion = await provider.complete(
        [
            Message(role=Role.system, content="be terse"),
            Message(role=Role.user, content="hi"),
        ],
        task="greet",
    )

    body = requests[0]
    assert completion.text == "hello"
    assert completion.usage.input_tokens == 5
    assert completion.usage.output_tokens == 2
    assert body["system"] == "be terse"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
