"""Group a document's chunks into token-bounded windows without splitting a chunk."""

from collections.abc import Iterable, Sequence

from busybee.ingest.chunker import chunk_with_prefix
from busybee.llm import count_tokens
from busybee.schema.documents import Chunk


def make_windows(chunks: Iterable[Chunk], window_tokens: int) -> list[list[Chunk]]:
    """Return consecutive non-empty windows whose chunk tokens stay within the budget.

    A single chunk larger than the budget still becomes its own window, because a chunk is
    the smallest unit that can carry a page-exact citation.
    """
    if window_tokens < 1:
        raise ValueError("window_tokens must be at least 1")
    windows: list[list[Chunk]] = []
    current: list[Chunk] = []
    used = 0
    for chunk in chunks:
        tokens = count_tokens(chunk_with_prefix(chunk))
        if current and used + tokens > window_tokens:
            windows.append(current)
            current = []
            used = 0
        current.append(chunk)
        used += tokens
    if current:
        windows.append(current)
    return windows


def chunk_window_text(chunk: Chunk) -> str:
    """Render one chunk with the id the model must cite."""
    return f"[{chunk.chunk_id}]\n{chunk_with_prefix(chunk)}"


def window_text(chunks: Sequence[Chunk]) -> str:
    """Render a window as id-prefixed chunk texts separated by blank lines."""
    return "\n\n".join(chunk_window_text(chunk) for chunk in chunks)
