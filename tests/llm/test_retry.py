"""Tests for retry classification, the time budget, backoff cap, and immediate failures."""

import json
import logging

import httpx
import pytest

from busybee.llm import retry as retry_module
from busybee.llm.messages import Message, Role
from busybee.llm.openai_compatible import OpenAICompatibleProvider
from busybee.llm.retry import call_with_retry, is_retryable


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

        monkeypatch.setattr(retry_module, "_sleep", sleep)
        monkeypatch.setattr(retry_module, "_now", lambda: self.now)


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


async def test_retryable_statuses_and_transport_errors() -> None:
    assert is_retryable(StatusError(429))
    assert is_retryable(StatusError(503))
    assert not is_retryable(StatusError(400))
    assert is_retryable(ConnectionError("connection reset"))


async def test_retries_stop_when_the_budget_is_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    clock.install(monkeypatch)
    attempts = 0

    async def always_fails(attempt: int) -> None:
        nonlocal attempts
        attempts = attempt
        raise StatusError(503)

    with pytest.raises(StatusError):
        await call_with_retry(always_fails, budget_s=300)

    assert attempts > 5
    assert max(clock.sleeps) <= 60
    assert clock.now <= 300 + 1e-6


async def test_budget_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    clock.install(monkeypatch)
    monkeypatch.setenv("BUSYBEE_LLM_RETRY_BUDGET_S", "10")

    async def always_fails() -> None:
        raise StatusError(429)

    with pytest.raises(StatusError):
        await call_with_retry(always_fails)

    assert 0 < clock.now <= 10 + 1e-6


async def test_non_retryable_error_fails_on_first_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def bad_request(attempt: int) -> None:
        nonlocal attempts
        attempts = attempt
        raise StatusError(400)

    with pytest.raises(StatusError):
        await call_with_retry(bad_request)

    assert attempts == 1


async def test_zero_argument_operations_are_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def no_sleep(seconds: float) -> None:
        return None

    async def eventually_succeeds() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise StatusError(429)
        return "done"

    monkeypatch.setattr(retry_module, "_sleep", no_sleep)

    assert await call_with_retry(eventually_succeeds) == "done"
    assert calls == 3


def completion_body(text: str) -> dict:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def provider_with(handler) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "m", base_url="http://test/v1", api_key="k", http_client=httpx.MockTransport(handler)
    )


MESSAGES = [Message(role=Role.user, content="hi")]


async def test_three_connection_failures_then_success(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    clock.install(monkeypatch)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=completion_body("ok"))

    with caplog.at_level(logging.WARNING, logger="busybee.llm.retry"):
        completion = await provider_with(handler).complete(MESSAGES)

    assert completion.text == "ok"
    assert calls == 4
    assert len(clock.sleeps) == 3
    retries = [r for r in caplog.records if r.name == "busybee.llm.retry" and r.levelno == 30]
    assert len(retries) == 3


async def test_connection_failures_beyond_the_budget_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    clock.install(monkeypatch)
    monkeypatch.setenv("BUSYBEE_LLM_RETRY_BUDGET_S", "120")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(Exception, match="Connection error"):
        await provider_with(handler).complete(MESSAGES)

    assert 120 - 1e-6 <= clock.now <= 120 + 1e-6


async def test_client_errors_fail_fast_and_server_errors_are_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    clock.install(monkeypatch)
    statuses = [503, 429, 200]

    def flaky(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        if status == 200:
            return httpx.Response(200, json=completion_body(json.dumps({"a": 1})))
        return httpx.Response(status, json={"error": {"message": "busy"}})

    assert (await provider_with(flaky).complete(MESSAGES)).text == '{"a": 1}'

    seen = 0

    def bad_request(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        return httpx.Response(400, json={"error": {"message": "bad"}})

    with pytest.raises(Exception, match="bad"):
        await provider_with(bad_request).complete(MESSAGES)
    assert seen == 1
