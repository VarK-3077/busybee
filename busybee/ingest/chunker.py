"""Split page text into page-bounded chunks with exact character offsets.

Offsets always satisfy `page_text[char_start:char_end] == chunk.text`, which is what the source
viewer relies on to highlight a chunk. Table blocks in the page text are delimited by sentinel
lines `[TABLE: <header cells>]` ... `[/TABLE]` (written by the PDF loader). When a chunk starts
inside such a block (`table_header_prefix=True`, the default), the block's `[TABLE: ...]` line
is stored in `Chunk.prefix` instead of being spliced into `text`: the body keeps exact offsets
and consumers that embed or show a chunk to a model use `chunk.prefix + "\n" + chunk.text`
(see `chunk_with_prefix`). Chunks starting at or before the opening line need no prefix.
"""

import re

import tiktoken

from busybee.schema.documents import Chunk
from busybee.schema.ids import make_chunk_id, make_doc_id

_SENTENCE_CLOSERS = "\"')]}"
_TABLE_OPEN = re.compile(r"^\[TABLE: .*\]$", re.MULTILINE)
_TABLE_CLOSE = re.compile(r"^\[/TABLE\]$", re.MULTILINE)
_ENCODING: tiktoken.Encoding | None = None
_ENCODING_UNAVAILABLE = False


def count_tokens(text: str) -> int:
    """Count cl100k_base tokens, falling back to a rough character estimate."""
    global _ENCODING, _ENCODING_UNAVAILABLE
    if not text:
        return 0
    if not _ENCODING_UNAVAILABLE:
        try:
            if _ENCODING is None:
                _ENCODING = tiktoken.get_encoding("cl100k_base")
            return len(_ENCODING.encode(text))
        except Exception:
            _ENCODING_UNAVAILABLE = True
    return max(1, len(text) // 4)


def _unit_spans(text: str) -> list[tuple[int, int]]:
    """Return spans of sentence- or line-sized units with leading whitespace skipped."""
    spans: list[tuple[int, int]] = []
    length = len(text)
    start = 0
    while start < length and text[start].isspace():
        start += 1
    index = start
    while index < length:
        char = text[index]
        if char in "\r\n":
            if index > start and text[start:index].strip():
                spans.append((start, index))
            start = index + 1
            while start < length and text[start].isspace():
                start += 1
            index = start
            continue
        if char in ".!?":
            end = index + 1
            while end < length and text[end] in _SENTENCE_CLOSERS:
                end += 1
            if end >= length or text[end].isspace():
                if end > start and text[start:end].strip():
                    spans.append((start, end))
                start = end
                while start < length and text[start].isspace():
                    start += 1
                index = start
                continue
            index = end
            continue
        index += 1
    end = length
    while end > start and text[end - 1].isspace():
        end -= 1
    if end > start:
        spans.append((start, end))
    return spans


def _table_header_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (body_start, body_end, header_line) for each sentinel-delimited table block."""
    spans: list[tuple[int, int, str]] = []
    for opening in _TABLE_OPEN.finditer(text):
        closing = _TABLE_CLOSE.search(text, opening.end())
        spans.append((opening.end(), closing.start() if closing else len(text), opening.group(0)))
    return spans


def _prefix_at(spans: list[tuple[int, int, str]], position: int) -> str:
    for body_start, body_end, header in spans:
        if body_start <= position < body_end:
            return header
    return ""


def chunk_with_prefix(chunk: Chunk) -> str:
    """Return the chunk text a reader or model should see: table header line first, if any."""
    return f"{chunk.prefix}\n{chunk.text}" if chunk.prefix else chunk.text


def chunk_page(
    doc_id: str,
    page_no: int,
    text: str,
    target_tokens: int = 700,
    overlap_tokens: int = 80,
    table_header_prefix: bool = True,
) -> list[Chunk]:
    """Greedily pack units into chunks of about target_tokens, repeating tail units."""
    spans = _unit_spans(text)
    if not spans:
        return []
    normalised_doc_id = make_doc_id(doc_id)
    unit_tokens = [count_tokens(text[start:end]) for start, end in spans]
    table_spans = _table_header_spans(text) if table_header_prefix else []
    chunks: list[Chunk] = []
    first_unit = 0
    while first_unit < len(spans):
        last_unit = first_unit
        total_tokens = 0
        while last_unit < len(spans):
            if last_unit > first_unit and total_tokens + unit_tokens[last_unit] > target_tokens:
                break
            total_tokens += unit_tokens[last_unit]
            last_unit += 1
            if total_tokens >= target_tokens:
                break
        char_start = spans[first_unit][0]
        char_end = spans[last_unit - 1][1]
        index = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=make_chunk_id(normalised_doc_id, page_no, index),
                doc_id=normalised_doc_id,
                page_no=page_no,
                index_in_page=index,
                text=text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                prefix=_prefix_at(table_spans, char_start),
            )
        )
        if last_unit >= len(spans):
            break
        tail_unit = last_unit - 1
        overlap = 0
        while tail_unit > first_unit and overlap + unit_tokens[tail_unit] <= overlap_tokens:
            overlap += unit_tokens[tail_unit]
            tail_unit -= 1
        first_unit = tail_unit + 1
    return chunks
