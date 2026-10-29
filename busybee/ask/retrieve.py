"""Load a finished run's vector index and documents, and fetch the chunks relevant to a question.

The embedder comes from the environment (`BUSYBEE_EMBED_PROVIDER`), so a question is embedded
the same way the run's chunks were. Chunks scoring at or below `MIN_SCORE` are not relevant.
"""

from pathlib import Path

from busybee.index.embedder.protocol import Embedder
from busybee.index.search import search
from busybee.index.store import VectorStore
from busybee.schema.documents import Document, ScoredChunk
from busybee.schema.io import read_models

TOP_K = 8
MIN_SCORE = 0.05


def load_run_store(workspace: Path) -> VectorStore:
    """Read the run's index directory, raising FileNotFoundError when the run has no index."""
    index_dir = workspace / "index"
    if not (index_dir / "vectors.npy").is_file():
        raise FileNotFoundError(f"no vector index in {index_dir}")
    return VectorStore.load(index_dir)


def load_run_documents(workspace: Path) -> dict[str, Document]:
    """Return the run's documents keyed by doc_id, empty when the corpus file is absent."""
    path = workspace / "corpus" / "documents.json"
    if not path.is_file():
        return {}
    return {document.doc_id: document for document in read_models(path, Document)}


async def retrieve(
    store: VectorStore, embedder: Embedder, question: str, k: int = TOP_K
) -> list[ScoredChunk]:
    """Return up to k relevant chunks for the question, best first."""
    hits = await search(store, embedder, question, k=k)
    return [hit for hit in hits if hit.score > MIN_SCORE]
