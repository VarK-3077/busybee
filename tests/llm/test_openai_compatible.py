"""Tests for the OpenAI-compatible provider over an injected MockTransport."""

import json
from typing import Any

import httpx

from busybee.llm.messages import Message, Role
from busybee.llm.openai_compatible import OpenAICompatibleProvider


def chat_completion(text: str, model: str = "test-model") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
    }


async def test_complete_sends_a_chat_request_and_parses_usage() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=chat_completion("hello there"))

    provider = OpenAICompatibleProvider(
        "test-model",
        base_url="http://test/v1",
        api_key="test",
        http_client=httpx.MockTransport(handler),
    )

    completion = await provider.complete(
        [Message(role=Role.user, content="say hello")],
        temperature=0.2,
        max_tokens=128,
        task="greet",
    )

    assert completion.text == "hello there"
    assert completion.model == "test-model"
    assert completion.usage.input_tokens == 7
    assert completion.usage.output_tokens == 4
    assert completion.latency_s >= 0.0
    assert requests[0]["model"] == "test-model"
    assert requests[0]["messages"] == [{"role": "user", "content": "say hello"}]
    assert requests[0]["temperature"] == 0.2
    assert requests[0]["max_tokens"] == 128


async def test_json_schema_is_sent_in_response_format_and_system_message() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=chat_completion('{"answer": 4}'))

    provider = OpenAICompatibleProvider(
        "test-model",
        base_url="http://test/v1",
        api_key="test",
        http_client=httpx.MockTransport(handler),
    )
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}

    completion = await provider.complete(
        [Message(role=Role.user, content="two plus two?")],
        json_schema=schema,
        task="math",
    )

    body = requests[0]
    assert completion.text == '{"answer": 4}'
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert body["messages"][0]["role"] == "system"
    assert '"answer"' in body["messages"][0]["content"]
