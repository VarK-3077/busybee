"""Read rating rationales first and hand their key points to every other document's windows.

Rating rationales are short and say what the rating agency saw as strengths, weaknesses and
triggers. `extract_rating_first(documents, aids, run_group)` extracts the documents of kind
`rating_rationale` first, builds `rating_digest` from their finished notebook entries (no extra
LLM call): entries by importance, then reading order, until `DIGEST_TOKENS` (800) are used,
written back in reading order as "- statement" lines with duplicates removed. That digest goes
into the prompt of every other document as "what the rating agency flagged". Without rating
rationales, or with nothing but rating rationales, the documents run in one group as before.
`run_group(documents, aids)` extracts a group of documents concurrently and returns one notebook
per document in the given order; the result here is in the original document order.
"""

from collections.abc import Awaitable, Callable, Sequence

from busybee.llm import count_tokens
from busybee.schema.documents import Document, DocumentKind
from busybee.schema.facts import NotebookEntry

from .aids import ReadingAids

DIGEST_TOKENS = 800
GroupRunner = Callable[[Sequence[Document], ReadingAids], Awaitable[list[list[NotebookEntry]]]]


def rating_digest(entries: Sequence[NotebookEntry], max_tokens: int = DIGEST_TOKENS) -> str:
    """The most important entry statements as bullet lines, within `max_tokens`, in order."""
    ranked = sorted(range(len(entries)), key=lambda index: (-entries[index].importance, index))
    chosen: list[int] = []
    seen: set[str] = set()
    used = 0
    for index in ranked:
        statement = " ".join(entries[index].statement.split())
        if not statement or statement.casefold() in seen:
            continue
        cost = count_tokens(f"- {statement}\n")
        if used + cost > max_tokens:
            continue
        seen.add(statement.casefold())
        chosen.append(index)
        used += cost
    return "\n".join(f"- {' '.join(entries[index].statement.split())}" for index in sorted(chosen))


async def extract_rating_first(
    documents: Sequence[Document], aids: ReadingAids, run_group: GroupRunner
) -> list[list[NotebookEntry]]:
    """Notebooks per document (original order), rating rationales read first."""
    rated = [d for d in documents if d.kind is DocumentKind.rating_rationale]
    others = [d for d in documents if d.kind is not DocumentKind.rating_rationale]
    if not rated or not others:
        return await run_group(documents, aids)
    rated_notebooks = await run_group(rated, aids)
    digest = rating_digest([entry for notebook in rated_notebooks for entry in notebook])
    other_notebooks = await run_group(others, aids.with_flagged(digest))
    by_id = {
        document.doc_id: notebook
        for group, notebooks in ((rated, rated_notebooks), (others, other_notebooks))
        for document, notebook in zip(group, notebooks, strict=True)
    }
    return [by_id[document.doc_id] for document in documents]
