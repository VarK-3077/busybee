"""Embeddings from any OpenAI-compatible `/v1/embeddings` endpoint.

The AsyncOpenAI client is built on first use so importing the package does not require a key
or a reachable server. Responses are ordered by their index field, then normalised to unit
rows. This is the production path for NIM, vLLM, LM Studio, and OpenAI itself.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np

from busybee.index.embedder.normalise import normalise_rows

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536
BATCH_SIZE = 64


class OpenAICompatibleEmbedder:
    """Embedder backed by an OpenAI-compatible embeddings endpoint."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        dim: int = DEFAULT_DIM,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self.name = f"openai_compatible:{model}"
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.dim = dim
        self.batch_size = batch_size
        self._client: Any = None

    def _client_instance(self) -> Any:
        """Create the async client once, on first use."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key or "EMPTY")
        return self._client

    async def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return L2-normalised embeddings for every text, batched for the endpoint."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        client = self._client_instance()
        vectors: list[list[float]] = []
        inputs = list(texts)
        for start in range(0, len(inputs), self.batch_size):
            batch = inputs[start : start + self.batch_size]
            response = await client.embeddings.create(model=self.model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise ValueError(
                    f"embedding endpoint returned {len(ordered)} vectors for {len(batch)} texts"
                )
            vectors.extend(item.embedding for item in ordered)
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.size:
            self.dim = int(matrix.shape[1])
        return normalise_rows(matrix)
