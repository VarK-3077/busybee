"""Embed the run corpus and search it locally.

Public entry points: `run_index` builds the store, `search` / `batch_search` query it,
`get_chunk` resolves citations, `VectorStore` loads or saves the index, and
`embedder_from_env` selects the configured embedder.
"""

from busybee.index.build_index import run_index
from busybee.index.embedder import (
    Embedder,
    HashingEmbedder,
    LocalEmbedder,
    OpenAICompatibleEmbedder,
    embedder_from_env,
)
from busybee.index.search import batch_search, get_chunk, search
from busybee.index.store import VectorStore, load_store, save_store

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "LocalEmbedder",
    "OpenAICompatibleEmbedder",
    "VectorStore",
    "batch_search",
    "embedder_from_env",
    "get_chunk",
    "load_store",
    "run_index",
    "save_store",
    "search",
]
