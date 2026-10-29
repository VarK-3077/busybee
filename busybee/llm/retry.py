"""Budgeted exponential backoff for transport errors, timeouts, 429 and 5xx responses.

A retryable failure is retried with exponential backoff and jitter, never sleeping more than
`MAX_DELAY_S` (60 s) between attempts, until the total retry budget is spent. The budget clock
starts at the first failure, not at the first attempt: an attempt that hangs until its request
timeout (30 minutes by default) must not use up the whole budget and leave the call with no
retry at all. The budget is
`BUSYBEE_LLM_RETRY_BUDGET_S` seconds (default 900, i.e. 15 minutes) so a vLLM server that
crashes and reloads for several minutes does not kill the run. Other errors (4xx except 429,
schema errors) fail on the first attempt. Each retry logs one line on the `busybee.llm.retry`
logger. `max_attempts` optionally adds a hard cap on the number of attempts.
"""

import asyncio
import inspect
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable

import httpx
from anthropic import APIConnectionError as AnthropicConnectionError
from anthropic import APITimeoutError as AnthropicTimeoutError
from openai import APIConnectionError as OpenAIConnectionError
from openai import APITimeoutError as OpenAITimeoutError

try:
    import httpx2
except ImportError:
    httpx2 = None

logger = logging.getLogger("busybee.llm.retry")

BUDGET_ENV = "BUSYBEE_LLM_RETRY_BUDGET_S"
DEFAULT_BUDGET_S = 900.0
MAX_DELAY_S = 60.0
_BASE_DELAY = 1.0


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _now() -> float:
    return time.monotonic()


def retry_budget_s() -> float:
    """Return the total retry budget in seconds from the environment (default 900)."""
    try:
        return max(0.0, float(os.environ.get(BUDGET_ENV, DEFAULT_BUDGET_S)))
    except ValueError:
        return DEFAULT_BUDGET_S


def _status_code(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if status is None:
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _request_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [
        httpx.RequestError,
        OSError,
        OpenAIConnectionError,
        OpenAITimeoutError,
        AnthropicConnectionError,
        AnthropicTimeoutError,
    ]
    if httpx2 is not None:
        errors.append(httpx2.RequestError)
    return tuple(errors)


_RETRYABLE_ERRORS = _request_errors()
_CONNECTION_ERRORS: tuple[type[BaseException], ...] = (
    httpx.TransportError,
    ConnectionError,
    OpenAIConnectionError,
    AnthropicConnectionError,
)


def is_retryable(error: BaseException) -> bool:
    """Return whether an error should be retried after backoff."""
    status = _status_code(error)
    if status == 429 or (status is not None and 500 <= status < 600):
        return True
    return isinstance(error, _RETRYABLE_ERRORS)


class UnreachableWatch:
    """Logs "endpoint unreachable" once, with the base URL, after repeated connection errors.

    Call `failed(error)` for every failed request and `succeeded()` for every good one. A run of
    `THRESHOLD` consecutive connection errors or timeouts logs one error line; the line is armed
    again only after a success, so a dead ssh tunnel is named once instead of on every retry.
    """

    THRESHOLD = 3

    def __init__(self, url: str) -> None:
        self.url = url
        self._streak = 0
        self._announced = False

    def succeeded(self) -> None:
        self._streak = 0
        self._announced = False

    def failed(self, error: BaseException) -> None:
        if not isinstance(error, _CONNECTION_ERRORS):
            return
        self._streak += 1
        if self._streak >= self.THRESHOLD and not self._announced:
            self._announced = True
            logger.error(
                "endpoint unreachable: %s (%d consecutive connection errors, last %s); "
                "is the ssh tunnel up?",
                self.url,
                self._streak,
                type(error).__name__,
            )


def _wants_attempt(operation: Callable[..., Awaitable[object]]) -> bool:
    try:
        signature = inspect.signature(operation)
    except (TypeError, ValueError):
        return True
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            return True
    return False


async def call_with_retry[ResultT](
    operation: Callable[..., Awaitable[ResultT]],
    *,
    budget_s: float | None = None,
    max_attempts: int | None = None,
    base_delay: float = _BASE_DELAY,
    max_delay: float = MAX_DELAY_S,
) -> ResultT:
    """Call operation(attempt) until it succeeds, fails fatally, or the retry budget is spent."""
    wants_attempt = _wants_attempt(operation)
    budget = retry_budget_s() if budget_s is None else budget_s
    first_failure: float | None = None
    attempt = 0
    while True:
        attempt += 1
        attempt_started = _now()
        try:
            if wants_attempt:
                return await operation(attempt)
            return await operation()
        except Exception as error:
            if first_failure is None:
                first_failure = _now()
            remaining = budget - (_now() - first_failure)
            exhausted = remaining <= 0 or (max_attempts is not None and attempt >= max_attempts)
            if exhausted or not is_retryable(error):
                raise
            delay = min(max_delay, base_delay * (2 ** min(attempt - 1, 16)))
            delay = min(max_delay, delay * random.uniform(0.5, 1.5), remaining)
            logger.warning(
                "llm retry %d after %s: %s (attempt took %.1fs); "
                "sleeping %.1fs, %.0fs of %.0fs budget left",
                attempt,
                type(error).__name__,
                str(error)[:200],
                _now() - attempt_started,
                delay,
                remaining,
                budget,
            )
            await _sleep(delay)


async def retry_with_backoff[ResultT](
    operation: Callable[..., Awaitable[ResultT]],
    *,
    budget_s: float | None = None,
    max_attempts: int | None = None,
    base_delay: float = _BASE_DELAY,
    max_delay: float = MAX_DELAY_S,
) -> ResultT:
    """Alias for call_with_retry with keyword retry settings."""
    return await call_with_retry(
        operation,
        budget_s=budget_s,
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
    )
