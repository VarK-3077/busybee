"""Page-exact rate (deterministic): the share of citations whose quote is in the cited chunk.

A citation is page-exact when its chunk exists in the corpus, its page number matches the
chunk's page, and its non-empty quote is a substring of the chunk text once whitespace and
case are normalised. The quote may also come from the chunk's table header line (`prefix`),
since models read the chunk as `chunk_with_prefix`, so the prefixed text is checked. Citations
of figures the bank supplied (`source == "bank_input"`, chunk `REQ:p1:c1`, no document) are not
document citations and are left out of the count. No LLM is involved.
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from busybee.ingest.chunker import chunk_with_prefix
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, VerifiedFact

from .common import ratio


class PageExactResult(BaseModel):
    """Page-exact rate and the offending citations as 'fact_id -> chunk_id'."""

    page_exact: float | None = None
    exact: int = 0
    total: int = 0
    failures: list[str] = Field(default_factory=list)


def _squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def citation_is_page_exact(citation: Citation, chunks_by_id: Mapping[str, Chunk]) -> bool:
    """True when the quote is a substring of the cited chunk (with its header) on the cited page."""
    chunk = chunks_by_id.get(citation.chunk_id)
    if chunk is None or chunk.page_no != citation.page_no or not citation.quote.strip():
        return False
    return _squash(citation.quote) in _squash(chunk_with_prefix(chunk))


def compute_page_exact(
    facts: Sequence[VerifiedFact], chunks_by_id: Mapping[str, Chunk]
) -> PageExactResult:
    """Return the page-exact rate over all citations of all facts."""
    total = 0
    failures: list[str] = []
    for fact in facts:
        for citation in fact.citations:
            if citation.source == "bank_input":
                continue
            total += 1
            if not citation_is_page_exact(citation, chunks_by_id):
                failures.append(f"{fact.fact_id} -> {citation.chunk_id}")
    return PageExactResult(
        page_exact=ratio(total - len(failures), total),
        exact=total - len(failures),
        total=total,
        failures=failures,
    )
