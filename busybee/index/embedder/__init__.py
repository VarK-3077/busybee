"""Embedder implementations selected by the vector index.

The protocol is the only thing search and build_index depend on; the concrete classes are
re-exported here for callers that want to choose an implementation explicitly, as tests and
the synthetic end-to-end run do with the hashing embedder.
"""

from busybee.index.embedder.hashing import HashingEmbedder
from busybee.index.embedder.local import LocalEmbedder
from busybee.index.embedder.normalise import normalise_rows
from busybee.index.embedder.openai_compatible import OpenAICompatibleEmbedder
from busybee.index.embedder.protocol import Embedder
from busybee.index.embedder.registry import embedder_from_env

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "LocalEmbedder",
    "OpenAICompatibleEmbedder",
    "embedder_from_env",
    "normalise_rows",
]
