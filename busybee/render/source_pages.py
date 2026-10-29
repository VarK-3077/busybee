"""Render one source page per document, with page-exact chunk anchors and text."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from jinja2 import Environment

from busybee.render.links import original_filename, pdf_href
from busybee.schema.documents import Chunk, Document, Page


def chunk_text(chunk: Chunk, page: Page | None, previous: Chunk | None) -> str:
    """Return the chunk's new text, starting where the previous chunk ended."""
    start = chunk.char_start
    if previous is not None and previous.char_end > start:
        start = previous.char_end
    end = chunk.char_end
    if page is not None and 0 <= start < end <= len(page.text):
        return page.text[start:end]
    if previous is not None:
        overlap = max(0, previous.char_end - chunk.char_start)
        if overlap < len(chunk.text):
            return chunk.text[overlap:]
    return chunk.text


def page_views(pages: Sequence[Page], chunks: Sequence[Chunk]) -> list[dict[str, object]]:
    """Group chunks by page and trim each one to the text after its predecessor."""
    chunks_by_page: dict[int, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_page[chunk.page_no].append(chunk)
    pages_by_number = {page.page_no: page for page in pages}
    views: list[dict[str, object]] = []
    for page_no in sorted(chunks_by_page):
        page = pages_by_number.get(page_no)
        ordered = sorted(
            chunks_by_page[page_no], key=lambda chunk: (chunk.index_in_page, chunk.char_start)
        )
        previous: Chunk | None = None
        chunk_views: list[dict[str, object]] = []
        for chunk in ordered:
            chunk_views.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "index_in_page": chunk.index_in_page,
                    "text": chunk_text(chunk, page, previous),
                }
            )
            previous = chunk
        views.append({"page_no": page_no, "chunks": chunk_views})
    return views


def render_source_page(
    environment: Environment,
    document: Document,
    pages: Sequence[Page],
    chunks: Sequence[Chunk],
) -> str:
    """Render one document's pages with a section per chunk."""
    views = page_views(pages, chunks)
    first_page = int(views[0]["page_no"]) if views else 1
    short_hash = f"{document.sha256[:12]}…" if len(document.sha256) > 12 else document.sha256
    return environment.get_template("source.html").render(
        root="../",
        document=document,
        pages=views,
        page_count=len(pages),
        original_name=original_filename(document),
        pdf_available=bool(document.source_path),
        pdf_href=lambda page_no: pdf_href(document, page_no),
        first_page=first_page,
        short_hash=short_hash,
    )
