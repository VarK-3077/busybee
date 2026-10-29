"""Tests for token counting, character fallback, and token-bounded truncation."""

import pytest

from busybee.llm import tokens as tokens_module
from busybee.llm.tokens import count_tokens, truncate_to_tokens


def test_count_tokens_is_zero_for_empty_text() -> None:
    assert count_tokens("") == 0


def test_count_tokens_counts_words() -> None:
    assert count_tokens("hello world") > 0


def test_truncate_to_tokens_respects_the_limit() -> None:
    text = "The borrower reported strong revenue growth across all segments. " * 20
    truncated = truncate_to_tokens(text, 10)

    assert truncated != text
    assert count_tokens(truncated) <= 10


def test_truncate_to_tokens_keeps_short_text() -> None:
    assert truncate_to_tokens("short", 10) == "short"
    assert truncate_to_tokens("short", 0) == ""


def test_character_fallback_when_tiktoken_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tokens_module, "_encoding", None)
    monkeypatch.setattr(tokens_module, "_encoding_failed", True)

    assert count_tokens("abcdefgh") == 2
    assert count_tokens("abc") == 1
    assert truncate_to_tokens("abcdefghij", 1) == "abcd"
