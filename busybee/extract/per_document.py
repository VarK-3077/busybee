"""Read each document through its own rolling notebook, then merge the notebooks.

Each extract call gets an explicit output budget of `min(16000, 3000 + window_tokens // 2)`
tokens. When a reply is cut off (`StructuredOutputError.truncated`, whether by this budget or by a
lower server limit) the window is split in halves and each half is read, recursively to a single
chunk or MAX_SPLIT_DEPTH. A chunk that still truncates is read with a prompt asking for at most
25 entries by importance, and a warning with stage `extract.truncated` goes to the dropped list.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence

from busybee.llm import Message, Role, StructuredOutputError, complete_as, count_tokens
from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk, Document
from busybee.schema.facts import DroppedEntry, NotebookEntry
from busybee.schema.run import RunConfig

from .aids import ReadingAids
from .condense import condense_entries
from .condensed import condense_notebook
from .notebook import Proposal, add_entries, apply_supersedes, merge_notebooks
from .policy_focus import apply_policy_importance
from .prompts import (
    LIMITED_ENTRIES_INSTRUCTION,
    MAX_LIMITED_ENTRIES,
    WindowOutput,
    build_user_prompt,
    system_prompt,
)
from .rating_first import extract_rating_first
from .slots import extract_slot
from .windows import make_windows, window_text

MAX_OUTPUT_TOKENS = 16000
MAX_SPLIT_DEPTH = 3
WindowCallback = Callable[[int, list[NotebookEntry]], None]


def extract_max_tokens(window_tokens: int) -> int:
    """Output token budget for one extract call over a window of window_tokens."""
    return min(MAX_OUTPUT_TOKENS, 3000 + window_tokens // 2)


def extract_timeout_s(max_tokens: int) -> float:
    """Per-request timeout for an extract call: 120 s plus 4 tokens per second of decoding."""
    return float(120 + max_tokens // 4)


def _truncation_warning(
    window: Sequence[Chunk], *, doc_id: str | None, window_no: int, reason: str
) -> DroppedEntry:
    ids = ", ".join(chunk.chunk_id for chunk in window)
    placeholder = NotebookEntry(
        entry_id=f"TRUNCATED:{window[0].chunk_id}",
        statement=f"(extract reply truncated for chunks {ids})",
        doc_id=doc_id or "",
        window_no=window_no,
    )
    return DroppedEntry(entry=placeholder, reason=reason, stage="extract.truncated")


async def _read_window(
    window: Sequence[Chunk],
    *,
    notebook: str,
    window_no: int,
    doc_id: str | None,
    doc_title: str,
    position: str,
    provider: Provider,
    max_tokens: int,
    dropped: list[DroppedEntry] | None = None,
    depth: int = 0,
    checklist: str = "",
    flagged: str = "",
) -> list[Proposal]:
    """Read a window; a truncated reply is split in halves, down to one chunk or MAX_SPLIT_DEPTH."""

    async def ask(limited: bool) -> list[Proposal]:
        prompt = build_user_prompt(
            notebook,
            window_text(window),
            window_no=window_no,
            doc_id=doc_id or "",
            doc_title=doc_title,
            position=position,
            flagged=flagged,
        )
        messages = [
            Message(role=Role.system, content=system_prompt(checklist)),
            Message(
                role=Role.user,
                content=prompt + LIMITED_ENTRIES_INSTRUCTION if limited else prompt,
            ),
        ]
        output = await complete_as(
            provider,
            messages,
            WindowOutput,
            task="extract",
            max_tokens=max_tokens,
            timeout_s=extract_timeout_s(max_tokens),
        )
        return [*output.entries, *output.records]

    try:
        return await ask(limited=False)
    except StructuredOutputError as error:
        if not error.truncated:
            raise
        if len(window) > 1 and depth < MAX_SPLIT_DEPTH:
            middle = len(window) // 2
            entries: list[Proposal] = []
            for half in (window[:middle], window[middle:]):
                entries.extend(
                    await _read_window(
                        half,
                        notebook=notebook,
                        window_no=window_no,
                        doc_id=doc_id,
                        doc_title=doc_title,
                        position=position,
                        provider=provider,
                        max_tokens=max_tokens,
                        dropped=dropped,
                        depth=depth + 1,
                        checklist=checklist,
                        flagged=flagged,
                    )
                )
            return entries
    reason = f"reply truncated at max_tokens={max_tokens}; re-read with at most "
    reason += f"{MAX_LIMITED_ENTRIES} entries, the remainder was not extracted"
    try:
        entries = await ask(limited=True)
    except StructuredOutputError as error:
        if not error.truncated:
            raise
        reason = "reply truncated even with the limited-entries prompt; nothing extracted"
        entries = []
    if dropped is not None:
        dropped.append(
            _truncation_warning(window, doc_id=doc_id, window_no=window_no, reason=reason)
        )
    return entries


async def extract_windows(
    chunks: Sequence[Chunk],
    *,
    cfg: RunConfig,
    provider: Provider,
    chunks_by_id: Mapping[str, Chunk],
    doc_id: str | None,
    doc_title: str = "",
    dropped: list[DroppedEntry] | None = None,
    on_window: WindowCallback | None = None,
    window_offset: int = 0,
    aids: ReadingAids | None = None,
) -> list[NotebookEntry]:
    """Read chunks sequentially through rolling windows and return the active entries."""
    return await extract_window_list(
        make_windows(chunks, cfg.window_tokens),
        cfg=cfg,
        provider=provider,
        chunks_by_id=chunks_by_id,
        doc_id=doc_id,
        doc_title=doc_title,
        dropped=dropped,
        on_window=on_window,
        window_offset=window_offset,
        aids=aids,
    )


async def extract_window_list(
    windows: Sequence[Sequence[Chunk]],
    *,
    cfg: RunConfig,
    provider: Provider,
    chunks_by_id: Mapping[str, Chunk],
    doc_id: str | None,
    doc_title: str = "",
    dropped: list[DroppedEntry] | None = None,
    on_window: WindowCallback | None = None,
    window_offset: int = 0,
    position: str = "",
    aids: ReadingAids | None = None,
) -> list[NotebookEntry]:
    """Run one rolling notebook over the given windows; `position` tells the model where."""
    history: list[NotebookEntry] = []
    active: list[NotebookEntry] = []
    for index, window in enumerate(windows, start=1):
        window_no = window_offset + index
        async with extract_slot(cfg.extract_concurrency):
            window_entries = await _read_window(
                window,
                notebook=condense_notebook(active),
                window_no=window_no,
                doc_id=doc_id,
                doc_title=doc_title,
                position=position,
                provider=provider,
                max_tokens=extract_max_tokens(cfg.window_tokens),
                dropped=dropped,
                checklist=aids.checklist if aids is not None else "",
                flagged=aids.flagged if aids is not None else "",
            )
        new_entries, new_dropped = add_entries(
            window_entries,
            doc_id=doc_id,
            window_no=window_no,
            chunks_by_id=chunks_by_id,
            existing=history,
            window_chunks=window,
        )
        if dropped is not None:
            dropped.extend(new_dropped)
        history.extend(new_entries)
        active = apply_supersedes(
            [*active, *new_entries],
            check=new_entries,
            history_ids=(entry.entry_id for entry in history),
        )
        if on_window is not None:
            on_window(window_no, new_entries)
        if count_tokens(condense_notebook(active)) > cfg.notebook_budget_tokens:
            active = await condense_entries(
                active, provider, budget_tokens=cfg.notebook_budget_tokens
            )
    return active


async def extract_document(
    doc: Document,
    chunks: Sequence[Chunk],
    cfg: RunConfig,
    provider: Provider,
    *,
    chunks_by_id: Mapping[str, Chunk] | None = None,
    dropped: list[DroppedEntry] | None = None,
    on_window: WindowCallback | None = None,
    aids: ReadingAids | None = None,
) -> list[NotebookEntry]:
    """Extract one document's notebook in a single sequential window stream."""
    mapping = (
        dict(chunks_by_id)
        if chunks_by_id is not None
        else {chunk.chunk_id: chunk for chunk in chunks}
    )
    entries = await extract_windows(
        chunks,
        cfg=cfg,
        provider=provider,
        chunks_by_id=mapping,
        doc_id=doc.doc_id,
        doc_title=doc.title,
        dropped=dropped,
        on_window=on_window,
        aids=aids,
    )
    return apply_policy_importance(entries, aids.focus if aids is not None else None)


async def extract_per_document(
    documents: Sequence[Document],
    chunks_by_doc: Mapping[str, Sequence[Chunk]],
    cfg: RunConfig,
    provider: Provider,
    *,
    chunks_by_id: Mapping[str, Chunk] | None = None,
    dropped: list[DroppedEntry] | None = None,
    on_window: WindowCallback | None = None,
    aids: ReadingAids | None = None,
) -> list[NotebookEntry]:
    """Extract every document concurrently (rating rationales first), merge in document order."""
    mapping = (
        dict(chunks_by_id)
        if chunks_by_id is not None
        else {
            chunk.chunk_id: chunk for doc_chunks in chunks_by_doc.values() for chunk in doc_chunks
        }
    )

    async def run_group(
        group: Sequence[Document], group_aids: ReadingAids
    ) -> list[list[NotebookEntry]]:
        return list(
            await asyncio.gather(
                *(
                    extract_document(
                        document,
                        chunks_by_doc.get(document.doc_id, []),
                        cfg,
                        provider,
                        chunks_by_id=mapping,
                        dropped=dropped,
                        on_window=on_window,
                        aids=group_aids,
                    )
                    for document in group
                )
            )
        )

    return merge_notebooks(await extract_rating_first(documents, aids or ReadingAids(), run_group))


extract_corpus_per_document = extract_per_document
