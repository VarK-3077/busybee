"""Anthropic Messages provider with the system prompt extracted from the messages."""

import os
from typing import Any

from anthropic import AsyncAnthropic

from .messages import Completion, Message, Usage
from .openai_compatible import coerce_http_client
from .provider import complete_and_record, llm_timeout_s, schema_instruction, split_system
from .retry import call_with_retry


class AnthropicProvider:
    """A chat provider for Anthropic's Messages API."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        http_client: Any = None,
        name: str = "anthropic",
        timeout: float | None = None,
    ) -> None:
        self.name = name
        self.model = model
        client_options: dict[str, Any] = {
            "api_key": api_key or os.getenv("ANTHROPIC_API_KEY") or "not-needed",
            "max_retries": 0,
        }
        if base_url is not None:
            client_options["base_url"] = base_url
        if http_client is not None:
            client_options["http_client"] = coerce_http_client(http_client)
        client_options["timeout"] = llm_timeout_s() if timeout is None else timeout
        self._client = AsyncAnthropic(**client_options)

    async def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        task: str = "",
        timeout_s: float | None = None,
    ) -> Completion:
        """Complete a conversation after moving system turns out of the chat list."""
        system, chat = split_system(messages)
        if json_schema is not None:
            instruction = schema_instruction(json_schema)
            system = f"{system}\n\n{instruction}" if system else instruction
        chat_messages = [
            {"role": message.role.value, "content": message.content} for message in chat
        ]
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system:
            request["system"] = system
        if timeout_s is not None:
            request["timeout"] = timeout_s

        async def call() -> tuple[str, Usage, str | None]:
            response = await self._client.messages.create(**request)
            text = "".join(
                block.text for block in response.content if getattr(block, "text", None) is not None
            )
            usage = Usage(
                input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
            )
            stop = getattr(response, "stop_reason", None)
            return text, usage, "length" if stop == "max_tokens" else stop

        async def attempt(attempt_no: int) -> Completion:
            return await complete_and_record(
                model=self.model,
                messages=messages,
                task=task,
                attempt=attempt_no,
                request=call,
            )

        return await call_with_retry(attempt)


ClaudeProvider = AnthropicProvider
