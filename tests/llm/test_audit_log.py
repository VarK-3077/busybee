"""Tests for JSONL audit entries and one line per provider attempt, including retries."""

import json
from pathlib import Path

import httpx
import pytest

from busybee.llm import retry as retry_module
from busybee.llm.audit_log import AuditEntry, configure, record
from busybee.llm.messages import Message, Role, Usage
from busybee.llm.openai_compatible import OpenAICompatibleProvider


def chat_completion(text: str, model: str = "test-model") -> dict[str, object]:
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
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


async def test_record_writes_one_json_line_per_entry(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "llm_log.jsonl"
    configure(path)

    await record(
        AuditEntry(
            task="extract",
            model="mock",
            messages=[Message(role=Role.user, content="hello")],
            text="world",
            usage=Usage(input_tokens=1, output_tokens=2),
            latency_s=0.5,
            attempt=1,
        )
    )
    await record(
        {
            "task": "verify",
            "model": "mock",
            "messages": [Message(role=Role.user, content="check")],
            "text": "ok",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "latency_s": 0.1,
            "attempt": 1,
        }
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert len(entries) == 2
    assert entries[0]["task"] == "extract"
    assert entries[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert entries[0]["usage"] == {"input_tokens": 1, "output_tokens": 2}
    assert entries[1]["task"] == "verify"
    assert "ts" in entries[1]


async def test_audit_log_records_every_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "llm_log.jsonl"
    configure(path)
    started = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal started
        started += 1
        if started == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json=chat_completion("hello"))

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry_module, "_sleep", no_sleep)
    provider = OpenAICompatibleProvider(
        "test-model",
        base_url="http://test/v1",
        api_key="test",
        http_client=httpx.MockTransport(handler),
    )

    completion = await provider.complete(
        [Message(role=Role.user, content="hi")],
        task="verify",
    )

    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert completion.text == "hello"
    assert [entry["attempt"] for entry in entries] == [1, 2]
    assert entries[0]["text"] == ""
    assert entries[1]["text"] == "hello"
    assert entries[0]["task"] == "verify"
    assert entries[0]["model"] == "test-model"
