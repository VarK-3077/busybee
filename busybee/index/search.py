"""Cosine search over the local vector store.

Vectors are unit length, so a dot product is the cosine similarity and one matrix multiply
ranks every chunk for a query. `doc_kinds` filters before ranking, which keeps the top-k full
of the requested document types. `get_chunk` is the citation resolver used by later stages.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np

from busybee.index.embedder.normalise import normalise_rows
from busybee.index.embedder.protocol import Embedder
from busybee.index.store import VectorStore
from busybee.schema.documents import Chunk, ScoredChunk

StoreSource = VectorStore | str | Path
DocKindFilter = str | Iterable[str] | None


def _store(store: StoreSource) -> VectorStore:
    """Accept either an in-memory store or a directory written by VectorStore.save."""
    return store if isinstance(store, VectorStore) else VectorStore.load(store)


def _kind_value(kind: object) -> str:
    """Return the string value of a document kind, including DocumentKind members."""
    return str(getattr(kind, "value", kind))


def _allowed_kinds(doc_kinds: DocKindFilter) -> set[str] | None:
    """Turn the doc_kinds argument into a set of kind strings, or None for no filter."""
    if doc_kinds is None:
        return None
    if isinstance(doc_kinds, str):
        return {_kind_value(doc_kinds)}
    return {_kind_value(kind) for kind in doc_kinds}


def _candidate_indices(store: VectorStore, doc_kinds: DocKindFilter) -> np.ndarray:
    """Return row indices allowed by the optional document-kind filter."""
    allowed = _allowed_kinds(doc_kinds)
    if allowed is None:
        return np.arange(len(store.chunks), dtype=np.int64)
    return np.array(
        [
            index
            for index, meta in enumerate(store.meta)
            if _kind_value(meta.get("kind", "")) in allowed
        ],
        dtype=np.int64,
    )


def _top_k(
    store: VectorStore,
    scores: np.ndarray,
    candidates: np.ndarray,
    k: int,
) -> list[ScoredChunk]:
    """Return the highest-scoring candidates, preserving stable order on ties."""
    if k <= 0 or candidates.size == 0:
        return []
    candidate_scores = scores[candidates]
    order = np.argsort(-candidate_scores, kind="stable")[:k]
    return [
        ScoredChunk(
            chunk=store.chunks[int(candidates[position])],
            score=float(candidate_scores[position]),
        )
        for position in order
    ]


async def _embed_query(embedder: Embedder, query: str) -> np.ndarray:
    """Embed one query and return a single normalised vector."""
    matrix = np.asarray(await embedder.embed([query]), dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.shape[0] != 1:
        raise ValueError(f"embedder returned {matrix.shape[0]} rows for one query")
    return normalise_rows(matrix)[0]


async def search(
    store: StoreSource,
    embedder: Embedder,
    query: str,
    k: int = 8,
    doc_kinds: DocKindFilter = None,
) -> list[ScoredChunk]:
    """Return up to k chunks most similar to query, optionally filtered by document kind."""
    vector_store = _store(store)
    if k <= 0 or not vector_store.chunks:
        return []
    query_vector = await _embed_query(embedder, query)
    candidates = _candidate_indices(vector_store, doc_kinds)
    scores = vector_store.vectors @ query_vector
    return _top_k(vector_store, scores, candidates, k)


async def batch_search(
    store: StoreSource,
    embedder: Embedder,
    queries: Sequence[str],
    k: int = 8,
    doc_kinds: DocKindFilter = None,
) -> list[list[ScoredChunk]]:
    """Run several queries with one embedding call and return one ranked list per query."""
    vector_store = _store(store)
    query_list = list(queries)
    if not query_list:
        return []
    if k <= 0 or not vector_store.chunks:
        return [[] for _ in query_list]
    matrix = np.asarray(await embedder.embed(query_list), dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.shape[0] != len(query_list):
        raise ValueError(f"embedder returned {matrix.shape[0]} rows for {len(query_list)} queries")
    query_vectors = normalise_rows(matrix)
    candidates = _candidate_indices(vector_store, doc_kinds)
    scores = vector_store.vectors @ query_vectors.T
    return [
        _top_k(vector_store, scores[:, index], candidates, k) for index in range(len(query_list))
    ]


def get_chunk(store: StoreSource, chunk_id: str) -> Chunk | None:
    """Return the chunk with chunk_id, or None when the citation does not resolve."""
    vector_store = _store(store)
    for chunk in vector_store.chunks:
        if chunk.chunk_id == chunk_id:
            return chunk
    return None
