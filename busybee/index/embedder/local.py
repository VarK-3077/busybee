"""Local CPU embeddings through fastembed's BAAI/bge-small-en-v1.5 model.

The model is loaded on the first embed call so importing the index package stays cheap and
tests that use the hashing embedder never touch fastembed. Inference is blocking CPU work, so
it runs in a worker thread and the model itself batches at 64 texts.
"""

import asyncio
from collections.abc import Sequence
from typing import Any

import numpy as np

from busybee.index.embedder.normalise import normalise_rows

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM = 384
BATCH_SIZE = 64


class LocalEmbedder:
    """Fastembed embedder with a lazily loaded local sentence-transformer model."""

    def __init__(self, model_name: str = DEFAULT_MODEL, dim: int = DEFAULT_DIM) -> None:
        self.name = f"local:{model_name}"
        self.model_name = model_name
        self.dim = dim
        self._model: Any = None

    def _model_instance(self) -> Any:
        """Load the fastembed model once, on first use."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def _embed_sync(self, texts: list[str]) -> np.ndarray:
        """Run fastembed in the calling thread and normalise its output."""
        model = self._model_instance()
        vectors = [
            np.asarray(vector, dtype=np.float32)
            for vector in model.embed(texts, batch_size=BATCH_SIZE)
        ]
        matrix = np.vstack(vectors) if vectors else np.zeros((0, self.dim), dtype=np.float32)
        if matrix.size:
            self.dim = int(matrix.shape[1])
        return normalise_rows(matrix)

    async def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return L2-normalised embeddings without blocking the event loop."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return await asyncio.to_thread(self._embed_sync, list(texts))
