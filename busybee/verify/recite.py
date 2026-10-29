"""Re-cite a statement: search the vector store and keep the first chunk that supports it.

The statement itself is the query. Of the top-k hits (default 5, minus chunks to exclude),
those whose text lacks one of the statement's numbers are skipped without an LLM call; the
rest are judged by entailment concurrently, and the highest-ranked `supported` verdict wins.
Returns None when no chunk supports the statement.
"""

import asyncio
from collections.abc import Collection
from dataclasses import dataclass

from busybee.index import search
from busybee.index.embedder.protocol import Embedder
from busybee.index.store import VectorStore
from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk

from .entailment import Verdict, judge_entailment
from .number_match import statement_numbers_supported

DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class Recitation:
    """A chunk found through the vector store that supports a statement."""

    chunk: Chunk
    quote: str
    note: str


async def recite(
    statement: str,
    store: VectorStore,
    embedder: Embedder,
    provider: Provider,
    *,
    k: int = DEFAULT_TOP_K,
    exclude_chunk_ids: Collection[str] = (),
) -> Recitation | None:
    """Return the first supporting chunk and quote among the top-k search hits, or None."""
    hits = await search(store, embedder, statement, k=k)
    candidates = [
        hit.chunk
        for hit in hits
        if hit.chunk.chunk_id not in exclude_chunk_ids
        and statement_numbers_supported(statement, hit.chunk.text)[0]
    ]
    verdicts = await asyncio.gather(
        *(judge_entailment(statement, chunk.text, provider) for chunk in candidates)
    )
    for chunk, verdict in zip(candidates, verdicts, strict=True):
        if verdict.verdict is Verdict.supported:
            return Recitation(chunk=chunk, quote=verdict.quote, note=verdict.note)
    return None
