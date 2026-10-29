"""Choose the right page loader for a document from its file extension."""

from collections.abc import Callable
from pathlib import Path

from busybee.ingest.loaders.html import load_html_pages
from busybee.ingest.loaders.markdown import load_markdown_pages
from busybee.ingest.loaders.pdf import load_pdf_pages
from busybee.ingest.loaders.text import load_text_pages

_LOADERS: dict[str, Callable[[str | Path], list[str]]] = {
    ".pdf": load_pdf_pages,
    ".md": load_markdown_pages,
    ".markdown": load_markdown_pages,
    ".html": load_html_pages,
    ".htm": load_html_pages,
    ".txt": load_text_pages,
    ".text": load_text_pages,
}
SUPPORTED_EXTENSIONS = frozenset(_LOADERS)


def load_pages(path: str | Path) -> list[str]:
    """Return the page texts of a supported document, raising ValueError otherwise."""
    source = Path(path)
    loader = _LOADERS.get(source.suffix.lower())
    if loader is None:
        raise ValueError(f"unsupported document type: {source.suffix or source}")
    return loader(source)
