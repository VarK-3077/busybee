"""Public surface of the LLM provider layer: providers, structured output, and logging."""

from .anthropic import AnthropicProvider, ClaudeProvider
from .audit_log import AuditEntry, record
from .audit_log import configure as configure_audit_log
from .limiter import configure as configure_limiter
from .limiter import limited
from .messages import Completion, Message, Role, Usage
from .mock import CallRecord, MockProvider, load_fixtures
from .openai_compatible import OpenAICompatibleProvider, OpenAIProvider
from .provider import Provider
from .recording import RecordingProvider
from .registry import provider_from_env
from .retry import call_with_retry, is_retryable, retry_with_backoff
from .structured import StructuredOutputError, complete_as, extract_json_value
from .tokens import count_tokens, truncate_to_tokens

__all__ = [
    "AnthropicProvider",
    "ClaudeProvider",
    "AuditEntry",
    "CallRecord",
    "Completion",
    "Message",
    "MockProvider",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "Provider",
    "RecordingProvider",
    "Role",
    "StructuredOutputError",
    "Usage",
    "call_with_retry",
    "complete_as",
    "configure_audit_log",
    "configure_limiter",
    "count_tokens",
    "extract_json_value",
    "is_retryable",
    "limited",
    "load_fixtures",
    "provider_from_env",
    "record",
    "retry_with_backoff",
    "truncate_to_tokens",
]
