"""Split plain text into pages at form feeds."""

from pathlib import Path


def split_text_pages(text: str) -> list[str]:
    """Split plain text on form feeds and return stripped page texts."""
    pages = [page.strip() for page in text.split("\f")]
    while len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages or [""]


def load_text_pages(path: str | Path) -> list[str]:
    """Read a plain-text file and split it into pages."""
    return split_text_pages(Path(path).read_text(encoding="utf-8"))
