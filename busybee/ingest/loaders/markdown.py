"""Split markdown into pages at explicit HTML comments or form feeds."""

import re
from pathlib import Path

_PAGE_BREAK = re.compile(r"<!--\s*page\s*-->|\f", re.IGNORECASE)


def split_markdown_pages(text: str) -> list[str]:
    """Split markdown text on page markers and return stripped page texts."""
    pages = [page.strip() for page in _PAGE_BREAK.split(text)]
    while len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages or [""]


def load_markdown_pages(path: str | Path) -> list[str]:
    """Read a markdown file and split it into pages."""
    return split_markdown_pages(Path(path).read_text(encoding="utf-8"))
