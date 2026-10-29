"""Build the run's vector index from the corpus written by ingest.

The corpus is read directly through `busybee.schema.io`, so indexing does not depend on the
ingest package being importable. Chunks are embedded in batches of 64 and written to
`<workspace>/index/` as vectors.npy, meta.jsonl, and chunks.jsonl. Re-running on the same
corpus rewrites the same files, which is what lets orchestration retry the stage safely.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from busybee.index.embedder.protocol import Embedder
from busybee.index.embedder.registry import embedder_from_env
from busybee.index.store import VectorStore
from busybee.ingest.chunker import chunk_with_prefix
from busybee.schema.documents import Chunk, Document
from busybee.schema.io import read_jsonl, read_models

BATCH_SIZE = 64


async def _embed_chunks(embedder: Embedder, chunks: Sequence[Chunk]) -> np.ndarray:
    """Embed chunk texts in order, returning one aligned matrix."""
    if not chunks:
        return np.zeros((0, embedder.dim), dtype=np.float32)
    parts: list[np.ndarray] = []
    dim: int | None = None
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start : start + BATCH_SIZE]
        matrix = np.asarray(
            await embedder.embed([chunk_with_prefix(chunk) for chunk in batch]), dtype=np.float32
        )
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.shape[0] != len(batch):
            raise ValueError(f"embedder returned {matrix.shape[0]} vectors for {len(batch)} chunks")
        if dim is None:
            dim = int(matrix.shape[1])
        elif matrix.shape[1] != dim:
            raise ValueError("embedder returned inconsistent vector dimensions")
        parts.append(matrix)
    return np.vstack(parts)


async def run_index(
    workspace_dir: str | Path,
    embedder: Embedder | None = None,
) -> VectorStore:
    """Read the corpus, embed every chunk, and write the index directory."""
    workspace = workspace_dir if isinstance(workspace_dir, Path) else Path(workspace_dir)
    corpus = workspace / "corpus"
    chunks = read_jsonl(corpus / "chunks.jsonl", Chunk)
    documents = read_models(corpus / "documents.json", Document)
    doc_kinds = {document.doc_id: document.kind.value for document in documents}
    active_embedder = embedder if embedder is not None else embedder_from_env()
    vectors = await _embed_chunks(active_embedder, chunks)
    store = VectorStore(
        vectors=np.zeros((0, active_embedder.dim), dtype=np.float32),
        doc_kinds=doc_kinds,
    )
    store.add(chunks, vectors)
    store.save(workspace / "index")
    return store
