"""Environment-driven embedder selection, including the offline default."""

import pytest

from busybee.index.embedder.hashing import HashingEmbedder
from busybee.index.embedder.local import LocalEmbedder
from busybee.index.embedder.openai_compatible import OpenAICompatibleEmbedder
from busybee.index.embedder.registry import embedder_from_env


def test_default_is_the_offline_hashing_fallback() -> None:
    assert isinstance(embedder_from_env({}), HashingEmbedder)


def test_explicit_hashing_provider() -> None:
    embedder = embedder_from_env({"BUSYBEE_EMBED_PROVIDER": "hashing"})
    assert isinstance(embedder, HashingEmbedder)
    assert embedder.dim == 256


def test_local_provider_is_lazy() -> None:
    embedder = embedder_from_env(
        {"BUSYBEE_EMBED_PROVIDER": "local", "BUSYBEE_EMBED_MODEL": "BAAI/bge-small-en-v1.5"}
    )
    assert isinstance(embedder, LocalEmbedder)
    assert embedder.name == "local:BAAI/bge-small-en-v1.5"
    assert embedder.dim == 384
    assert embedder._model is None


def test_openai_compatible_provider_reads_endpoint_settings() -> None:
    embedder = embedder_from_env(
        {
            "BUSYBEE_EMBED_PROVIDER": "openai_compatible",
            "BUSYBEE_EMBED_MODEL": "custom-embed",
            "BUSYBEE_EMBED_BASE_URL": "http://localhost:8000/v1",
            "BUSYBEE_EMBED_API_KEY": "secret",
            "BUSYBEE_EMBED_DIM": "1024",
        }
    )
    assert isinstance(embedder, OpenAICompatibleEmbedder)
    assert embedder.model == "custom-embed"
    assert embedder.base_url == "http://localhost:8000/v1"
    assert embedder.api_key == "secret"
    assert embedder.dim == 1024


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        embedder_from_env({"BUSYBEE_EMBED_PROVIDER": "nonsense"})
