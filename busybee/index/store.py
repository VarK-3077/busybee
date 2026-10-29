"""A small on-disk vector store: vectors.npy plus aligned chunk metadata.

Rows of the matrix line up one-for-one with `chunks.jsonl` and `meta.jsonl`, so search never
has to join files at query time. Meta carries the document kind for filtering; the full Chunk
objects are kept beside the index so citations can be resolved without re-reading the corpus.
Every file is replaced atomically, which makes an interrupted rebuild leave a usable index.
"""

import io
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from busybee.schema.documents import Chunk
from busybee.schema.io import read_jsonl

VECTORS_FILE = "vectors.npy"
META_FILE = "meta.jsonl"
CHUNKS_FILE = "chunks.jsonl"

ChunkMeta = dict[str, Any]


def _as_path(directory: str | Path) -> Path:
    """Normalise a directory argument to Path."""
    return directory if isinstance(directory, Path) else Path(directory)


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    """Replace path with payload only after the complete write succeeds."""
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_bytes(payload)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _write_jsonl_atomic(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write JSON lines atomically."""
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    _write_bytes_atomic(path, payload.encode("utf-8"))


def _read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    """Read non-empty JSONL lines as dictionaries."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _meta_for(chunk: Chunk, kind: str) -> ChunkMeta:
    """Build the compact metadata row stored next to one vector."""
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "page_no": chunk.page_no,
        "kind": kind,
    }


@dataclass
class VectorStore:
    """Normalised chunk vectors with their chunks and search metadata."""

    vectors: np.ndarray
    chunks: list[Chunk] = field(default_factory=list)
    meta: list[ChunkMeta] = field(default_factory=list)
    doc_kinds: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return the number of indexed chunks."""
        return len(self.chunks)

    def add(self, chunks: Sequence[Chunk], vectors: np.ndarray) -> None:
        """Append chunks and their aligned vectors, recording each chunk's document kind."""
        items = list(chunks)
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError("vectors must be a 2-D array")
        if matrix.shape[0] != len(items):
            raise ValueError(f"got {matrix.shape[0]} vectors for {len(items)} chunks")
        if self.vectors.ndim != 2:
            raise ValueError("store vectors must be a 2-D array")
        if self.vectors.shape[0] == 0:
            if self.vectors.shape[1] not in {0, matrix.shape[1]}:
                raise ValueError("new vectors have a different dimension")
            self.vectors = matrix.copy()
        else:
            if matrix.shape[1] != self.vectors.shape[1]:
                raise ValueError("new vectors have a different dimension")
            self.vectors = np.vstack([self.vectors, matrix])
        self.chunks.extend(items)
        self.meta.extend(
            _meta_for(chunk, self.doc_kinds.get(chunk.doc_id, "other")) for chunk in items
        )

    def save(self, directory: str | Path) -> Path:
        """Write vectors, metadata, and chunks into directory atomically."""
        target = _as_path(directory)
        target.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        np.save(buffer, self.vectors, allow_pickle=False)
        _write_bytes_atomic(target / VECTORS_FILE, buffer.getvalue())
        _write_jsonl_atomic(target / META_FILE, self.meta)
        _write_jsonl_atomic(
            target / CHUNKS_FILE,
            [chunk.model_dump(mode="json") for chunk in self.chunks],
        )
        return target

    @classmethod
    def load(cls, directory: str | Path) -> "VectorStore":
        """Read a store written by save, validating that all three files stay aligned."""
        source = _as_path(directory)
        vectors = np.load(source / VECTORS_FILE, allow_pickle=False).astype(np.float32, copy=False)
        chunks = read_jsonl(source / CHUNKS_FILE, Chunk)
        meta = _read_jsonl_dicts(source / META_FILE)
        if vectors.ndim != 2:
            raise ValueError("vectors.npy must contain a 2-D array")
        if len(chunks) != vectors.shape[0] or len(meta) != len(chunks):
            raise ValueError("index files are not aligned")
        doc_kinds = {
            str(row["doc_id"]): str(row["kind"])
            for row in meta
            if "doc_id" in row and "kind" in row
        }
        return cls(vectors=vectors, chunks=chunks, meta=meta, doc_kinds=doc_kinds)

    def chunks_by_id(self) -> dict[str, Chunk]:
        """Return a lookup from chunk id to chunk."""
        return {chunk.chunk_id: chunk for chunk in self.chunks}


def load_store(directory: str | Path) -> VectorStore:
    """Module-level convenience wrapper around VectorStore.load."""
    return VectorStore.load(directory)


def save_store(store: VectorStore, directory: str | Path) -> Path:
    """Module-level convenience wrapper around VectorStore.save."""
    return store.save(directory)
