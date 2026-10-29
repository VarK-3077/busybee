"""Build a provider from BUSYBEE_LLM_* environment variables and stage overrides."""

import importlib
import os
import re

from .anthropic import AnthropicProvider
from .mock import MockProvider, load_fixtures
from .openai_compatible import OpenAICompatibleProvider
from .provider import Provider

_DEFAULT_MODELS = {
    "mock": "mock",
    "openai_compatible": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}


def _stage_suffix(stage: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", stage.upper()).strip("_")


def _model_for(provider_name: str, stage: str | None) -> str:
    if stage:
        override = os.getenv(f"BUSYBEE_LLM_MODEL_{_stage_suffix(stage)}")
        if override:
            return override
    return os.getenv("BUSYBEE_LLM_MODEL") or _DEFAULT_MODELS.get(provider_name, "")


def provider_from_env(stage: str | None = None) -> Provider:
    """Return the configured provider, applying a per-stage model override."""
    name = (os.getenv("BUSYBEE_LLM_PROVIDER") or "mock").strip().lower()
    model = _model_for(name, stage)
    base_url = os.getenv("BUSYBEE_LLM_BASE_URL") or None
    api_key = os.getenv("BUSYBEE_LLM_API_KEY") or None

    if name in {"mock", "fixture", "fixtures"}:
        callable_spec = os.getenv("BUSYBEE_LLM_MOCK_CALLABLE")
        if callable_spec:
            module_name, _, function_name = callable_spec.partition(":")
            function = getattr(importlib.import_module(module_name), function_name)
            return MockProvider(function, model=model or "mock")
        directory = os.getenv("BUSYBEE_LLM_MOCK_DIR")
        responses = load_fixtures(directory) if directory else {}
        return MockProvider(responses, model=model or "mock")

    if name in {"openai_compatible", "openai", "vllm", "nim"}:
        return OpenAICompatibleProvider(model, base_url=base_url, api_key=api_key)

    if name in {"anthropic", "claude"}:
        return AnthropicProvider(model, base_url=base_url, api_key=api_key)

    raise ValueError(f"unknown BUSYBEE_LLM_PROVIDER: {name!r}")
