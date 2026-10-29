"""OpenAI-compatible chat provider for NIM, vLLM, LM Studio, and OpenAI endpoints."""

import inspect
import json
import logging
import os
import re
from typing import Any

import httpx
from openai import AsyncOpenAI, BadRequestError

from .messages import Completion, Message, Usage
from .provider import complete_and_record, llm_timeout_s, messages_with_schema
from .retry import UnreachableWatch, call_with_retry

DEFAULT_MAX_TOKENS = 4096
_STANDARD_SAMPLING = frozenset(
    {"temperature", "top_p", "frequency_penalty", "presence_penalty", "seed"}
)
_log = logging.getLogger(__name__)
_LIMIT_PATTERNS = (
    re.compile(r"\(\d+\s*>\s*(\d+)\s*-\s*(\d+)\)"),
    re.compile(
        r"maximum context length is (\d+).*?(\d+) in the messages", re.IGNORECASE | re.DOTALL
    ),
)
_DIRECT_LIMIT = re.compile(
    r"(?:less than or equal to|at most|maximum (?:value )?(?:is|of|allowed is)|max(?:imum)? "
    r"(?:output|completion) tokens (?:is|of))\s*(\d+)",
    re.IGNORECASE,
)

try:
    import httpx2
except ImportError:
    httpx2 = None


def _sdk_uses_httpx2() -> bool:
    try:
        from openai import _base_client
    except ImportError:
        return False
    return hasattr(_base_client, "httpx2")


class _LegacyAsyncTransport(httpx2.AsyncBaseTransport if httpx2 is not None else object):
    def __init__(self, transport: Any) -> None:
        self._transport = transport

    async def handle_async_request(self, request: Any) -> Any:
        content = await request.aread()
        legacy_request = httpx.Request(
            method=request.method,
            url=str(request.url),
            headers=list(request.headers.items()),
            content=content,
            extensions=dict(getattr(request, "extensions", None) or {}),
        )
        async_handler = getattr(self._transport, "handle_async_request", None)
        if async_handler is not None:
            legacy_response = await async_handler(legacy_request)
        else:
            legacy_response = self._transport.handle_request(legacy_request)
        if hasattr(legacy_response, "aread"):
            response_content = await legacy_response.aread()
        else:
            response_content = legacy_response.read()
        return httpx2.Response(
            status_code=legacy_response.status_code,
            headers=list(legacy_response.headers.items()),
            content=response_content,
        )

    async def aclose(self) -> None:
        close = getattr(self._transport, "aclose", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
            return
        close = getattr(self._transport, "close", None)
        if close is not None:
            close()


def coerce_http_client(http_client: Any) -> Any:
    if http_client is None or not _sdk_uses_httpx2() or httpx2 is None:
        return http_client
    if isinstance(http_client, httpx2.AsyncClient):
        return http_client
    if isinstance(http_client, httpx2.AsyncBaseTransport):
        return httpx2.AsyncClient(transport=http_client)
    if isinstance(http_client, httpx.AsyncClient):
        transport = getattr(http_client, "_transport", http_client)
        return httpx2.AsyncClient(transport=_LegacyAsyncTransport(transport))
    if hasattr(http_client, "handle_async_request") or hasattr(http_client, "handle_request"):
        return httpx2.AsyncClient(transport=_LegacyAsyncTransport(http_client))
    return http_client


def server_token_limit(message: str, requested: int) -> int | None:
    """Read the output-token maximum a server names in a 400 error, if smaller than requested."""
    found: int | None = None
    for pattern in _LIMIT_PATTERNS:
        match = pattern.search(message)
        if match:
            found = int(match.group(1)) - int(match.group(2))
            break
    if found is None:
        match = _DIRECT_LIMIT.search(message)
        found = int(match.group(1)) if match else None
    return found if found is not None and 0 < found < requested else None


def sampling_overrides() -> dict[str, Any]:
    """Return request fields from BUSYBEE_LLM_SAMPLING (JSON); non-OpenAI keys go in extra_body."""
    raw = os.getenv("BUSYBEE_LLM_SAMPLING", "").strip()
    if not raw:
        return {}
    values = json.loads(raw)
    standard = {key: values[key] for key in values if key in _STANDARD_SAMPLING}
    extra = {key: values[key] for key in values if key not in _STANDARD_SAMPLING}
    return {**standard, **({"extra_body": extra} if extra else {})}


def _response_format(json_schema: dict[str, Any], task: str) -> dict[str, Any]:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", task or "response").strip("_") or "response"
    return {
        "type": "json_schema",
        "json_schema": {"name": name[:64], "schema": json_schema, "strict": False},
    }


class OpenAICompatibleProvider:
    """A chat provider that speaks the OpenAI Chat Completions protocol."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        http_client: Any = None,
        name: str = "openai_compatible",
        timeout: float | None = None,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.default_max_tokens = default_max_tokens
        self.name = name
        self.model = model
        client_options: dict[str, Any] = {
            "base_url": base_url,
            "api_key": api_key or os.getenv("OPENAI_API_KEY") or "not-needed",
            "http_client": coerce_http_client(http_client),
            "max_retries": 0,
        }
        client_options["timeout"] = llm_timeout_s() if timeout is None else timeout
        self._client = AsyncOpenAI(**client_options)
        self._watch = UnreachableWatch(str(self._client.base_url))

    async def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        task: str = "",
        timeout_s: float | None = None,
    ) -> Completion:
        """Complete a conversation and parse the chat-completion response."""
        prepared = (
            messages_with_schema(messages, json_schema) if json_schema is not None else messages
        )
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [message.model_dump(mode="json") for message in prepared],
            "temperature": temperature,
            "max_tokens": self.default_max_tokens if max_tokens is None else max_tokens,
            **sampling_overrides(),
        }
        if timeout_s is not None:
            request["timeout"] = timeout_s
        if json_schema is not None:
            request["response_format"] = _response_format(json_schema, task)

        async def call() -> tuple[str, Usage, str | None]:
            try:
                response = await self._client.chat.completions.create(**request)
            except BadRequestError as error:
                limit = server_token_limit(str(error), request["max_tokens"])
                if limit is None:
                    raise
                _log.warning(
                    "server rejected max_tokens=%s for task %r; clamping to %s",
                    request["max_tokens"],
                    task,
                    limit,
                )
                request["max_tokens"] = limit
                response = await self._client.chat.completions.create(**request)
            choice = response.choices[0] if response.choices else None
            text = (choice.message.content or "") if choice is not None else ""
            raw_usage = getattr(response, "usage", None)
            usage = Usage(
                input_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
            )
            reason = getattr(choice, "finish_reason", None) if choice is not None else None
            return text, usage, reason

        async def attempt(attempt_no: int) -> Completion:
            try:
                completion = await complete_and_record(
                    model=self.model,
                    messages=messages,
                    task=task,
                    attempt=attempt_no,
                    request=call,
                )
            except Exception as error:
                self._watch.failed(error)
                raise
            self._watch.succeeded()
            return completion

        return await call_with_retry(attempt)


OpenAIProvider = OpenAICompatibleProvider
