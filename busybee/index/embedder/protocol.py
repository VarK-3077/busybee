"""The small embedder contract every provider implementation in this package satisfies.

An embedder turns a batch of texts into one float32 row per text. Rows are L2-normalised so
that a plain dot product is cosine similarity, which is what `busybee.index.search` relies on.
The name and dim fields let the store and logs describe the vectors without re-embedding.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    """A batch text embedder whose rows are L2-normalised float32 vectors."""

    name: str
    dim: int

    async def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return a (len(texts), dim) float32 matrix with unit-length rows."""
        ...
