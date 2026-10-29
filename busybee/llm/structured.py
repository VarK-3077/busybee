"""Ask a provider for JSON, extract it tolerantly, and validate it as a pydantic model."""

import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from .messages import Message, Role
from .provider import Provider, messages_with_schema
from .tokens import count_tokens

TRUNCATION_FRACTION = 0.98

_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class StructuredOutputError(RuntimeError):
    """Raised when every attempt at a validated structured reply fails."""

    def __init__(
        self, message: str, last_text: str = "", attempts: int = 0, truncated: bool = False
    ) -> None:
        super().__init__(message)
        self.truncated = truncated
        self.last_text = last_text
        self.text = last_text
        self.attempts = attempts


class TruncatedReplyError(ValueError):
    """The reply's top-level JSON value starts but never closes: the model was cut off."""


def _is_unclosed(text: str) -> bool:
    """True when text ends inside a string or with a bracket still open."""
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
    return in_string or depth > 0


def _top_level_value(candidate: str) -> Any:
    """Decode the first "{" or "[" of candidate as the whole reply; never a nested value."""
    start = min((i for i in (candidate.find("{"), candidate.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON object or array found in reply")
    body = candidate[start:]
    try:
        value, _ = json.JSONDecoder().raw_decode(body)
    except json.JSONDecodeError as error:
        if _is_unclosed(body):
            raise TruncatedReplyError(
                f"reply ends before its top-level JSON value closes: {error}"
            ) from error
        raise ValueError(f"malformed JSON: {error}") from error
    return value


def extract_json_value(text: str) -> Any:
    """Return the top-level JSON value of a reply, ignoring fences and surrounding prose.

    Raises TruncatedReplyError when that value is incomplete, never a nested object.
    """
    fenced = [match.group(1).strip() for match in _CODE_FENCE.finditer(text)]
    for candidate in [*fenced, text.strip()]:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        try:
            return _top_level_value(candidate)
        except TruncatedReplyError:
            raise
        except ValueError:
            continue
    raise ValueError("no JSON object or array found in reply")


def _retry_message(error: Exception) -> Message:
    return Message(
        role=Role.user,
        content=(
            "Your previous reply was invalid: "
            f"{error}. Reply again with only one valid JSON value matching the schema, "
            "minified on one line, without prose or Markdown fences."
        ),
    )


def _hit_limit(output_tokens: int, text: str, limits: Sequence[int]) -> bool:
    used = output_tokens or count_tokens(text)
    return any(used >= TRUNCATION_FRACTION * limit for limit in limits)


def _truncation_limits(provider: Provider, max_tokens: int | None) -> list[int]:
    default = getattr(provider, "default_max_tokens", None)
    return [limit for limit in (max_tokens, default) if isinstance(limit, int) and limit > 0]


async def complete_as[ModelT: BaseModel](
    provider: Provider,
    messages: list[Message],
    model: type[ModelT],
    *,
    task: str,
    retries: int = 2,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
) -> ModelT:
    """Complete, extract, and validate a model reply, re-prompting on failure."""
    json_schema = model.model_json_schema()
    conversation = messages_with_schema(messages, json_schema)
    last_text = ""
    last_error: Exception | None = None
    limit: dict[str, Any] = {} if max_tokens is None else {"max_tokens": max_tokens}
    if timeout_s is not None:
        limit["timeout_s"] = timeout_s
    limits = _truncation_limits(provider, max_tokens)
    for attempt in range(retries + 1):
        completion = await provider.complete(
            conversation, json_schema=json_schema, task=task, temperature=temperature, **limit
        )
        last_text = completion.text
        try:
            return model.model_validate(extract_json_value(last_text))
        except (ValueError, ValidationError) as error:
            last_error = error
            if (
                isinstance(error, TruncatedReplyError)
                or completion.finish_reason == "length"
                or _hit_limit(completion.usage.output_tokens, last_text, limits)
            ):
                raise StructuredOutputError(
                    f"reply truncated (output tokens {completion.usage.output_tokens}, "
                    f"finish_reason {completion.finish_reason}): {error}",
                    last_text,
                    attempt + 1,
                    truncated=True,
                ) from error
            if attempt >= retries:
                break
            conversation = [
                *conversation,
                Message(role=Role.assistant, content=last_text),
                _retry_message(error),
            ]
    raise StructuredOutputError(
        f"structured output failed after {retries + 1} attempts: {last_error}",
        last_text,
        retries + 1,
    ) from last_error
