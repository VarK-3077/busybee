"""Deterministic offline feature hashing over word unigrams and bigrams.

This is the embedder tests use and the registry falls back to when no provider is configured.
Tokens are hashed with blake2b rather than Python's salted `hash`, so vectors are identical
across processes and machines. Signed hashing keeps collisions from systematically inflating
similarity. No model is downloaded and no network is touched.
"""

import hashlib
import re
from collections.abc import Sequence

import numpy as np

from busybee.index.embedder.normalise import normalise_rows

_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_UNIGRAM_WEIGHT = 1.0
_BIGRAM_WEIGHT = 0.5


def _tokens(text: str) -> list[str]:
    """Lowercase a text and return its alphanumeric word tokens."""
    return _WORD_PATTERN.findall(text.lower())


def _bucket(token: str, dim: int) -> tuple[int, float]:
    """Map a token to a stable bucket index and a stable sign."""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dim, 1.0 if (value >> 63) & 1 else -1.0


def _embed_one(text: str, dim: int) -> np.ndarray:
    """Build one raw feature-hashed row before normalisation."""
    vector = np.zeros(dim, dtype=np.float32)
    tokens = _tokens(text)
    features: list[tuple[str, float]] = [(token, _UNIGRAM_WEIGHT) for token in tokens]
    features.extend(
        (f"{left} {right}", _BIGRAM_WEIGHT) for left, right in zip(tokens, tokens[1:], strict=False)
    )
    for feature, weight in features:
        index, sign = _bucket(feature, dim)
        vector[index] += sign * weight
    return vector


class HashingEmbedder:
    """Deterministic hashing embedder over word unigrams and bigrams."""

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.name = "hashing"
        self.dim = dim

    async def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return L2-normalised feature-hashed rows for every input text."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        matrix = np.vstack([_embed_one(text, self.dim) for text in texts])
        return normalise_rows(matrix)
