"""Read the whole corpus as one sequential rolling-notebook stream."""

from collections.abc import Mapping, Sequence

from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk, Document
from busybee.schema.facts import DroppedEntry, NotebookEntry
from busybee.schema.run import RunConfig

from .per_document import WindowCallback, extract_windows


async def extract_global(
    documents: Sequence[Document],
    chunks_by_doc: Mapping[str, Sequence[Chunk]],
    cfg: RunConfig,
    provider: Provider,
    *,
    chunks_by_id: Mapping[str, Chunk] | None = None,
    dropped: list[DroppedEntry] | None = None,
    on_window: WindowCallback | None = None,
) -> list[NotebookEntry]:
    """Feed all documents, in order, through one rolling window sequence."""
    ordered_chunks = [
        chunk for document in documents for chunk in chunks_by_doc.get(document.doc_id, [])
    ]
    mapping = (
        dict(chunks_by_id)
        if chunks_by_id is not None
        else {
            chunk.chunk_id: chunk for doc_chunks in chunks_by_doc.values() for chunk in doc_chunks
        }
    )
    return await extract_windows(
        ordered_chunks,
        cfg=cfg,
        provider=provider,
        chunks_by_id=mapping,
        doc_id=None,
        dropped=dropped,
        on_window=on_window,
    )


extract_corpus_global = extract_global
