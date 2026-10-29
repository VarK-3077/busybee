"""Rescue extract entries whose model reply carried no usable chunk id.

When the model returns an entry without (valid) citations, the evidence is usually still in the
window it was reading. `rescue_citations` looks only at that window's chunks. An entry with
numbers is attached to the chunks whose text (table prefix included) contains every one of its
numbers, provided exactly one or two chunks match. An entry without numbers is attached to the
single chunk sharing the most content tokens, provided at least `MIN_SHARED_TOKENS` are shared
and no other chunk ties. Anything else is left uncited so the caller drops it as before.
Rescued entries are flagged `citation_inferred`; verify still checks every citation later, and
`run_extract` lists them in `extract_rescued.json`.
"""

import re
from collections.abc import Sequence

from busybee.ingest.chunker import chunk_with_prefix
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, NotebookEntry
from busybee.verify.number_match import find_numbers, statement_numbers_supported

MIN_SHARED_TOKENS = 4
MAX_NUMBER_MATCHES = 2
RESCUED_FILE = "extract_rescued.json"
RESCUE_NOTE = "citation inferred from numbers"
_WORD = re.compile(r"[a-z][a-z0-9]{2,}")
_STOPWORDS = frozenset(
    "the and for with that this from was were has have had are its their which than into "
    "also been being such not but all any per can may will shall during under over about".split()
)


def _content_tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS}


def _citation(chunk: Chunk) -> Citation:
    return Citation(chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no)


def _by_numbers(statement: str, window: Sequence[Chunk]) -> list[Chunk]:
    return [
        chunk
        for chunk in window
        if statement_numbers_supported(statement, chunk_with_prefix(chunk))[0]
    ]


def _by_overlap(statement: str, window: Sequence[Chunk]) -> list[Chunk]:
    wanted = _content_tokens(statement)
    scored = [(len(wanted & _content_tokens(chunk_with_prefix(chunk))), chunk) for chunk in window]
    best = max((score for score, _ in scored), default=0)
    top = [chunk for score, chunk in scored if score == best]
    return top if best >= MIN_SHARED_TOKENS and len(top) == 1 else []


def rescue_citations(statement: str, window: Sequence[Chunk]) -> list[Citation]:
    """Return inferred citations for an uncited statement, or an empty list when unsure."""
    if find_numbers(statement):
        matches = _by_numbers(statement, window)
        if 1 <= len(matches) <= MAX_NUMBER_MATCHES:
            return [_citation(chunk) for chunk in matches]
        return []
    return [_citation(chunk) for chunk in _by_overlap(statement, window)]


def rescued_records(entries: Sequence[NotebookEntry]) -> list[dict[str, object]]:
    """Return the audit rows for `extract_rescued.json`: entry id, chunk ids and the note."""
    return [
        {
            "entry_id": entry.entry_id,
            "chunk_ids": [citation.chunk_id for citation in entry.citations],
            "note": RESCUE_NOTE,
        }
        for entry in entries
        if entry.citation_inferred
    ]
