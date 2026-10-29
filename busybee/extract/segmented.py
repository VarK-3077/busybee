"""Read each document as concurrent contiguous segments, each with its own rolling notebook.

A long document is cut into windows exactly as in `per_document` mode. The windows are then
grouped into K contiguous, balanced segments with
K = max(1, min(cfg.concurrency, n_windows // cfg.segment_min_windows)), so every segment has
at least `segment_min_windows` windows whenever a split happens. Each segment runs the usual
sequential rolling notebook (condensing, supersedes and all) while the segments of a document
and all documents run concurrently through `asyncio.gather`; the global LLM limiter bounds the
real parallelism. Each segment's prompt states which pages it is reading, so period and
context are not lost, and window numbers stay document-global.

Merge: segment notebooks are concatenated in document order and entry ids are renumbered
per document. A supersede link is only meaningful inside the segment that produced it, so it
is remapped through that segment's own id map, and a link to an entry already removed is
dropped; cross-segment duplicates are left to verify's dedupe. Each segment owns its dropped
list, joined in segment order, and nothing is appended to notebook.jsonl until the whole
merge is done, so the file order is deterministic. Importance is set per document after
the merge from the policy (see policy_focus.py).

Documents of kind rating_rationale are extracted first and their key points are added to the
prompt of every other document (see rating_first.py).

With `progress_path`, each finished segment is appended to the extract progress file (see
progress.py) and a segment already recorded there is reused without any LLM call, so a stage
that died halfway continues instead of restarting. Every segment is allowed to finish before
the first error is re-raised, so no completed segment is lost.
"""

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk, Document
from busybee.schema.facts import DroppedEntry, NotebookEntry
from busybee.schema.ids import make_entry_id
from busybee.schema.run import RunConfig

from .aids import ReadingAids
from .notebook import merge_notebooks
from .per_document import extract_window_list
from .policy_focus import apply_policy_importance
from .progress import load_segments, record_segment, segment_fingerprint
from .rating_first import extract_rating_first
from .windows import make_windows


def segment_count(n_windows: int, concurrency: int, segment_min_windows: int) -> int:
    """Return how many segments a document with `n_windows` windows is split into."""
    if n_windows <= 0:
        return 0
    return max(1, min(concurrency, n_windows // max(1, segment_min_windows)))


def split_segments[T](items: Sequence[T], count: int) -> list[list[T]]:
    """Split items into `count` contiguous parts whose sizes differ by at most one."""
    if count <= 0:
        return []
    base, extra = divmod(len(items), count)
    parts: list[list[T]] = []
    start = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        parts.append(list(items[start : start + size]))
        start += size
    return parts


def _position(segment: Sequence[Sequence[Chunk]], index: int, count: int, total_pages: int) -> str:
    """Describe the pages a segment covers; empty when the segment is the whole document."""
    if count <= 1:
        return ""
    pages = [chunk.page_no for window in segment for chunk in window]
    return (
        f"pages {min(pages)}–{max(pages)} of {total_pages} "
        f"(segment {index + 1} of {count} of this document)"
    )


def _renumber_document(
    segments: Sequence[Sequence[NotebookEntry]], doc_id: str
) -> list[NotebookEntry]:
    """Concatenate one document's segments, assign fresh ids, and remap in-segment supersedes."""
    merged: list[NotebookEntry] = []
    for segment in segments:
        new_ids = {
            entry.entry_id: make_entry_id(doc_id, len(merged) + offset)
            for offset, entry in enumerate(segment, start=1)
        }
        for entry in segment:
            supersedes = entry.supersedes
            merged.append(
                entry.model_copy(
                    update={
                        "entry_id": new_ids[entry.entry_id],
                        "doc_id": doc_id,
                        "supersedes": new_ids.get(supersedes) if supersedes else None,
                    }
                )
            )
    return merged


async def extract_document_segmented(
    doc: Document,
    chunks: Sequence[Chunk],
    cfg: RunConfig,
    provider: Provider,
    *,
    chunks_by_id: Mapping[str, Chunk],
    dropped: list[DroppedEntry] | None = None,
    progress_path: Path | None = None,
    aids: ReadingAids | None = None,
) -> list[NotebookEntry]:
    """Extract one document through concurrent segment notebooks and merge them in order."""
    windows = make_windows(chunks, cfg.window_tokens)
    count = segment_count(len(windows), cfg.concurrency, cfg.segment_min_windows)
    segments = split_segments(windows, count)
    total_pages = max((chunk.page_no for chunk in chunks), default=0)
    segment_dropped: list[list[DroppedEntry]] = [[] for _ in segments]
    offsets = [sum(len(s) for s in segments[:i]) for i in range(len(segments))]
    saved = load_segments(progress_path) if progress_path is not None else {}

    async def run_segment(index: int, segment: list[list[Chunk]]) -> list[NotebookEntry]:
        fingerprint = segment_fingerprint(segment, count)
        record = saved.get((doc.doc_id, index))
        if record is not None and record.fingerprint == fingerprint:
            segment_dropped[index].extend(record.dropped)
            return record.entries
        entries = await extract_window_list(
            segment,
            cfg=cfg,
            provider=provider,
            chunks_by_id=chunks_by_id,
            doc_id=doc.doc_id,
            doc_title=doc.title,
            dropped=segment_dropped[index],
            window_offset=offsets[index],
            position=_position(segment, index, count, total_pages),
            aids=aids,
        )
        if progress_path is not None:
            record_segment(
                progress_path, doc.doc_id, index, fingerprint, entries, segment_dropped[index]
            )
        return entries

    outcomes = await asyncio.gather(
        *(run_segment(index, segment) for index, segment in enumerate(segments)),
        return_exceptions=True,
    )
    results: list[list[NotebookEntry]] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
        results.append(outcome)
    if dropped is not None:
        for part in segment_dropped:
            dropped.extend(part)
    renumbered = _renumber_document(results, doc.doc_id)
    return apply_policy_importance(renumbered, aids.focus if aids is not None else None)


async def extract_segmented(
    documents: Sequence[Document],
    chunks_by_doc: Mapping[str, Sequence[Chunk]],
    cfg: RunConfig,
    provider: Provider,
    *,
    chunks_by_id: Mapping[str, Chunk] | None = None,
    dropped: list[DroppedEntry] | None = None,
    progress_path: Path | None = None,
    aids: ReadingAids | None = None,
) -> list[NotebookEntry]:
    """Extract all documents concurrently in segments (rating rationales first), merge in order."""
    mapping = (
        dict(chunks_by_id)
        if chunks_by_id is not None
        else {
            chunk.chunk_id: chunk for doc_chunks in chunks_by_doc.values() for chunk in doc_chunks
        }
    )
    document_dropped: dict[str, list[DroppedEntry]] = {d.doc_id: [] for d in documents}

    async def run_group(
        group: Sequence[Document], group_aids: ReadingAids
    ) -> list[list[NotebookEntry]]:
        outcomes = await asyncio.gather(
            *(
                extract_document_segmented(
                    document,
                    chunks_by_doc.get(document.doc_id, []),
                    cfg,
                    provider,
                    chunks_by_id=mapping,
                    dropped=document_dropped[document.doc_id],
                    progress_path=progress_path,
                    aids=group_aids,
                )
                for document in group
            ),
            return_exceptions=True,
        )
        notebooks: list[list[NotebookEntry]] = []
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
            notebooks.append(outcome)
        return notebooks

    notebooks = await extract_rating_first(documents, aids or ReadingAids(), run_group)
    if dropped is not None:
        for document in documents:
            dropped.extend(document_dropped[document.doc_id])
    return merge_notebooks(notebooks)
