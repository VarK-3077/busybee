"""Request-timeout plumbing: env default on the client, per-call override, retry log."""

import json
import logging
from typing import Any

import httpx
import pytest

from busybee.llm.anthropic import AnthropicProvider
from busybee.llm.messages import Message, Role
from busybee.llm.openai_compatible import OpenAICompatibleProvider
from busybee.llm.provider import llm_timeout_s
from busybee.llm.retry import call_with_retry

USER = [Message(role=Role.user, content="hi")]


def openai_reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def anthropic_reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    )


def test_timeout_env_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUSYBEE_LLM_TIMEOUT_S", raising=False)
    assert llm_timeout_s() == 1800.0
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "42")
    assert llm_timeout_s() == 42.0
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "bogus")
    assert llm_timeout_s() == 1800.0


def test_clients_are_built_with_the_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "77")
    openai = OpenAICompatibleProvider("m", base_url="http://t/v1", api_key="k")
    claude = AnthropicProvider("m", api_key="k")
    assert openai._client.timeout == 77.0
    assert claude._client.timeout == 77.0


async def test_per_call_timeout_override_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "500")
    seen: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions.get("timeout"))
        return openai_reply(request)

    provider = OpenAICompatibleProvider(
        "m", base_url="http://t/v1", api_key="k", http_client=httpx.MockTransport(handler)
    )
    await provider.complete(USER)
    await provider.complete(USER, timeout_s=33)
    assert seen[0]["read"] == 500.0
    assert seen[1]["read"] == 33.0


async def test_anthropic_per_call_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "500")
    seen: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions.get("timeout"))
        return anthropic_reply(request)

    provider = AnthropicProvider(
        "m", api_key="k", base_url="http://t", http_client=httpx.MockTransport(handler)
    )
    await provider.complete(USER)
    await provider.complete(USER, timeout_s=33)
    assert seen[0]["read"] == 500.0
    assert seen[1]["read"] == 33.0


async def test_timeout_retry_logs_elapsed_and_starts_the_budget_at_the_first_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import busybee.llm.retry as retry

    clock = [0.0]
    monkeypatch.setattr(retry, "_now", lambda: clock[0])

    async def no_sleep(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(retry, "_sleep", no_sleep)
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            clock[0] += 300.0
            raise httpx.ReadTimeout("Request timed out.")
        return "done"

    with caplog.at_level(logging.WARNING, logger="busybee.llm.retry"):
        assert await call_with_retry(operation, budget_s=900) == "done"
    line = caplog.messages[0]
    assert "attempt took 300.0s" in line
    assert "900s of 900s budget left" in line
    assert json.dumps(line)
