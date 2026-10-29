"""Tests for page-bounded chunking, exact offsets, and overlap."""

from busybee.ingest.chunker import chunk_page, count_tokens
from busybee.schema.ids import make_chunk_id


def long_text(count: int = 40) -> str:
    sentences = (
        f"Sentence number {number} contains a few useful words." for number in range(count)
    )
    return " ".join(sentences)


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_page("D1", 1, "   \n\n  ") == []


def test_short_text_is_one_chunk_with_exact_offsets() -> None:
    text = "Revenue was 100 crore. Profit was 12 crore."
    chunks = chunk_page("D1", 2, text)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == make_chunk_id("D1", 2, 0)
    assert chunk.index_in_page == 0
    assert chunk.text == text
    assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_chunk_offsets_are_exact_across_many_chunks() -> None:
    text = long_text()
    chunks = chunk_page("D1", 1, text, target_tokens=40, overlap_tokens=10)
    assert len(chunks) > 3
    for index, chunk in enumerate(chunks):
        assert chunk.chunk_id == make_chunk_id("D1", 1, index)
        assert chunk.index_in_page == index
        assert text[chunk.char_start : chunk.char_end] == chunk.text
        assert chunk.text


def test_consecutive_chunks_overlap_by_tail_sentences() -> None:
    text = long_text()
    chunks = chunk_page("D1", 1, text, target_tokens=50, overlap_tokens=25)
    assert len(chunks) > 2
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.char_start < previous.char_end
        shared = text[current.char_start : previous.char_end]
        assert shared
        assert previous.text.endswith(shared)
        assert current.text.startswith(shared)


def test_table_like_lines_remain_offset_exact() -> None:
    text = (
        "Covenant | Requirement | FY25\n"
        "Net debt / EBITDA | 3.5 | 2.7\n"
        "DSCR | 1.25 | 1.78\n"
        "Current ratio | 1.15 | 1.27"
    )
    chunks = chunk_page("D1", 1, text, target_tokens=10, overlap_tokens=4)
    assert chunks
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_count_tokens_is_positive_for_text() -> None:
    assert count_tokens("Revenue grew 10%.") > 0
    assert count_tokens("") == 0
