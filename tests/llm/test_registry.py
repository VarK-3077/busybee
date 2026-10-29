"""Tests for environment-driven provider selection and per-stage model overrides."""

import json
from pathlib import Path

import pytest

from busybee.llm.anthropic import AnthropicProvider
from busybee.llm.messages import Message, Role
from busybee.llm.mock import MockProvider
from busybee.llm.openai_compatible import OpenAICompatibleProvider
from busybee.llm.registry import provider_from_env


def test_mock_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUSYBEE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("BUSYBEE_LLM_MODEL", raising=False)
    monkeypatch.delenv("BUSYBEE_LLM_MODEL_VERIFY", raising=False)

    provider = provider_from_env()

    assert isinstance(provider, MockProvider)
    assert provider.name == "mock"
    assert provider.model == "mock"


def test_per_stage_model_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BUSYBEE_LLM_MODEL", "mock-large")
    monkeypatch.setenv("BUSYBEE_LLM_MODEL_VERIFY", "mock-small")

    stage_provider = provider_from_env("verify")
    default_provider = provider_from_env()

    assert isinstance(stage_provider, MockProvider)
    assert stage_provider.model == "mock-small"
    assert default_provider.model == "mock-large"


async def test_mock_fixtures_are_loaded_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "extract.json").write_text(
        json.dumps([{"task": "extract", "messages": [], "text": "fixture reply"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BUSYBEE_LLM_MOCK_DIR", str(tmp_path))
    monkeypatch.delenv("BUSYBEE_LLM_MODEL", raising=False)

    provider = provider_from_env("extract")
    completion = await provider.complete(
        [Message(role=Role.user, content="hi")],
        task="extract",
    )

    assert completion.text == "fixture reply"


def test_openai_provider_is_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("BUSYBEE_LLM_MODEL", "base-model")
    monkeypatch.setenv("BUSYBEE_LLM_MODEL_SCORES", "score-model")

    provider = provider_from_env("scores")

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "score-model"


def test_anthropic_provider_is_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("BUSYBEE_LLM_MODEL", "claude-test")

    provider = provider_from_env("infer")

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-test"


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "mystery")

    with pytest.raises(ValueError):
        provider_from_env()
