"""Incident: a hung attempt used the whole retry budget, and a dead tunnel was never named."""

import logging

import httpx
import openai
import pytest

from busybee.llm import retry as retry_module
from busybee.llm.messages import Message, Role
from busybee.llm.openai_compatible import OpenAICompatibleProvider
from busybee.llm.provider import verify_call_timeout_s
from busybee.llm.retry import call_with_retry, is_retryable

REQUEST = httpx.Request("POST", "http://127.0.0.1:8000/v1/chat/completions")


def test_timeouts_are_retryable() -> None:
    assert is_retryable(openai.APITimeoutError(request=REQUEST))
    assert is_retryable(httpx.ReadTimeout("slow"))


async def test_a_hung_attempt_does_not_consume_the_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0

    async def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    monkeypatch.setattr(retry_module, "_sleep", sleep)
    monkeypatch.setattr(retry_module, "_now", lambda: now)
    calls = 0

    async def hangs_once() -> str:
        nonlocal now, calls
        calls += 1
        if calls == 1:
            now += 1800
            raise openai.APITimeoutError(request=REQUEST)
        return "ok"

    assert await call_with_retry(hangs_once, budget_s=900) == "ok"
    assert calls == 2


def test_verify_timeout_is_capped_by_the_llm_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUSYBEE_VERIFY_TIMEOUT_S", raising=False)
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "1800")
    assert verify_call_timeout_s() == 600
    monkeypatch.setenv("BUSYBEE_LLM_TIMEOUT_S", "100")
    assert verify_call_timeout_s() == 100


async def test_repeated_connection_errors_log_endpoint_unreachable_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry_module, "_sleep", no_sleep)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts <= 6:
            raise httpx.ConnectError("refused", request=request)
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
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    provider = OpenAICompatibleProvider(
        "m",
        base_url="http://127.0.0.1:8000/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with caplog.at_level(logging.ERROR, logger="busybee.llm.retry"):
        completion = await provider.complete([Message(role=Role.user, content="x")], task="t")

    assert completion.text == "hi"
    unreachable = [r for r in caplog.records if "endpoint unreachable" in r.getMessage()]
    assert len(unreachable) == 1
    assert "127.0.0.1:8000" in unreachable[0].getMessage()
