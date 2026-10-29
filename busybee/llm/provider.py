"""The provider protocol plus shared helpers for audited, schema-guided calls."""

import json
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from .audit_log import AuditEntry, record
from .limiter import limited
from .messages import Completion, Message, Role, Usage


@runtime_checkable
class Provider(Protocol):
    """Anything that can complete a chat conversation and report its identity."""

    name: str
    model: str

    async def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: str = "",
        timeout_s: float | None = None,
    ) -> Completion: ...


TIMEOUT_ENV = "BUSYBEE_LLM_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 1800.0


def llm_timeout_s() -> float:
    """Request timeout in seconds from BUSYBEE_LLM_TIMEOUT_S (default 1800)."""
    try:
        value = float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


VERIFY_TIMEOUT_ENV = "BUSYBEE_VERIFY_TIMEOUT_S"
DEFAULT_VERIFY_TIMEOUT_S = 600.0


def verify_call_timeout_s() -> float:
    """Request timeout for short judge replies (entailment, relevance, conflicts), default 600.

    Never above `llm_timeout_s()`. A reply of a few hundred tokens that has not arrived after
    ten minutes means a hung connection (for example a stalled ssh tunnel), not slow decoding,
    so the attempt is abandoned and retried instead of blocking for the full 30 minutes.
    """
    try:
        value = float(os.environ.get(VERIFY_TIMEOUT_ENV, DEFAULT_VERIFY_TIMEOUT_S))
    except ValueError:
        value = DEFAULT_VERIFY_TIMEOUT_S
    if value <= 0:
        value = DEFAULT_VERIFY_TIMEOUT_S
    return min(value, llm_timeout_s())


def schema_instruction(json_schema: dict[str, Any]) -> str:
    """Return the JSON-only instruction that carries a schema to the model."""
    schema_text = json.dumps(json_schema, ensure_ascii=False, separators=(",", ":"))
    return (
        "Reply with one JSON value only, minified on a single line: no indentation, no "
        "line breaks between tokens, no prose, no Markdown code fences. "
        "The value must conform to this JSON schema:\n"
        f"{schema_text}"
    )


def messages_with_schema(
    messages: list[Message],
    json_schema: dict[str, Any],
) -> list[Message]:
    """Append the schema instruction to the first system turn, or prepend one."""
    instruction = schema_instruction(json_schema)
    prepared = [Message(role=message.role, content=message.content) for message in messages]
    for message in prepared:
        if message.role == Role.system:
            message.content = (
                f"{message.content}\n\n{instruction}" if message.content else instruction
            )
            return prepared
    return [Message(role=Role.system, content=instruction), *prepared]


def split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    """Return the combined system prompt and the non-system conversation turns."""
    system = "\n\n".join(
        message.content for message in messages if message.role == Role.system and message.content
    )
    chat = [message for message in messages if message.role != Role.system]
    return system, chat


async def complete_and_record(
    *,
    model: str,
    messages: list[Message],
    task: str,
    attempt: int,
    request: Callable[[], Awaitable[tuple[str, Usage] | tuple[str, Usage, str | None]]],
) -> Completion:
    """Run one provider request through the limiter and audit log.

    The request returns (text, usage) or (text, usage, finish_reason); a finish_reason of
    "length" means the server stopped the reply at its output-token limit.
    """
    async with limited():
        started = time.perf_counter()
        try:
            result = await request()
            text, usage = result[0], result[1]
            finish_reason = result[2] if len(result) > 2 else None
        except Exception:
            await record(
                AuditEntry(
                    task=task,
                    model=model,
                    messages=messages,
                    text="",
                    usage=Usage(),
                    latency_s=time.perf_counter() - started,
                    attempt=attempt,
                )
            )
            raise
        latency_s = time.perf_counter() - started
    await record(
        AuditEntry(
            task=task,
            model=model,
            messages=messages,
            text=text,
            usage=usage,
            latency_s=latency_s,
            attempt=attempt,
            finish_reason=finish_reason,
        )
    )
    return Completion(
        text=text, usage=usage, model=model, latency_s=latency_s, finish_reason=finish_reason
    )
