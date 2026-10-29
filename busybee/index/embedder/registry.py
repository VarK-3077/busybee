"""Build the configured embedder from environment variables.

`BUSYBEE_EMBED_PROVIDER` selects local, openai_compatible, or hashing; when it is unset the
deterministic hashing embedder is used so offline runs and tests need no model or network.
`BUSYBEE_EMBED_MODEL` overrides the model name, and the OpenAI-compatible path reads
`BUSYBEE_EMBED_BASE_URL` / `BUSYBEE_EMBED_API_KEY` with the LLM endpoint as a fallback.
"""

import os
from collections.abc import Mapping

from busybee.index.embedder.hashing import HashingEmbedder
from busybee.index.embedder.local import DEFAULT_MODEL as DEFAULT_LOCAL_MODEL
from busybee.index.embedder.local import LocalEmbedder
from busybee.index.embedder.openai_compatible import DEFAULT_MODEL as DEFAULT_OPENAI_MODEL
from busybee.index.embedder.openai_compatible import OpenAICompatibleEmbedder
from busybee.index.embedder.protocol import Embedder

DEFAULT_PROVIDER = "hashing"


def _dim_from_env(environ: Mapping[str, str], default: int) -> int:
    """Read an optional positive integer embedding dimension."""
    raw = environ.get("BUSYBEE_EMBED_DIM")
    if not raw:
        return default
    dim = int(raw)
    if dim <= 0:
        raise ValueError("BUSYBEE_EMBED_DIM must be positive")
    return dim


def embedder_from_env(environ: Mapping[str, str] | None = None) -> Embedder:
    """Return the embedder selected by the environment, defaulting to hashing."""
    env = os.environ if environ is None else environ
    provider = (env.get("BUSYBEE_EMBED_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    model = env.get("BUSYBEE_EMBED_MODEL")

    if provider == "hashing":
        return HashingEmbedder()
    if provider in {"local", "fastembed"}:
        return LocalEmbedder(model_name=model or DEFAULT_LOCAL_MODEL)
    if provider in {"openai_compatible", "openai"}:
        base_url = env.get("BUSYBEE_EMBED_BASE_URL") or env.get("BUSYBEE_LLM_BASE_URL")
        api_key = (
            env.get("BUSYBEE_EMBED_API_KEY")
            or env.get("BUSYBEE_LLM_API_KEY")
            or env.get("OPENAI_API_KEY")
        )
        return OpenAICompatibleEmbedder(
            model=model or DEFAULT_OPENAI_MODEL,
            base_url=base_url,
            api_key=api_key,
            dim=_dim_from_env(env, 1536),
        )
    raise ValueError(
        f"unknown BUSYBEE_EMBED_PROVIDER {provider!r}; expected local, openai_compatible, "
        "or hashing"
    )
