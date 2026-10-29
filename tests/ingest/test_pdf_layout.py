"""Tests for column-aware PDF text, header-carrying tables and chunk table prefixes."""

from pathlib import Path

import pymupdf

from busybee.ingest.chunker import chunk_page, chunk_with_prefix
from busybee.ingest.loaders.pdf import load_pdf_pages

LEFT_LINES = [f"Left column sentence number {i} about revenue growth." for i in range(8)]
RIGHT_LINES = [f"Right column sentence number {i} about debt repayment." for i in range(8)]
HEADERS = ["Particulars", "March 31, 2026", "March 31, 2025"]
ROWS = [
    ("Revenue", "1,23,456.78", "(1,234.50)"),
    ("Profit", "70,346.28", "9,000.00"),
    ("Borrowings", "5,500.00", "4,400.00"),
    ("Net worth", "88,000.10", "77,000.20"),
]


def draw_grid(page: pymupdf.Page, top: float, rows: list[tuple[str, ...]]) -> None:
    for row_index, row in enumerate(rows):
        y = top + row_index * 22
        for col_index, cell in enumerate(row):
            x = 72 + col_index * 150
            page.draw_rect(pymupdf.Rect(x, y, x + 150, y + 22))
            page.insert_text((x + 4, y + 15), cell, fontsize=9)


def make_layout_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        for index, line in enumerate(LEFT_LINES):
            page.insert_text((60, 72 + index * 14), line, fontsize=7)
        for index, line in enumerate(RIGHT_LINES):
            page.insert_text((330, 72 + index * 14), line, fontsize=7)
        draw_grid(page, 260, [tuple(HEADERS), *ROWS])
        document.save(path)


def test_two_column_text_is_read_column_by_column(tmp_path: Path) -> None:
    path = tmp_path / "layout.pdf"
    make_layout_pdf(path)
    text = load_pdf_pages(path)[0]
    assert text.index(LEFT_LINES[-1]) < text.index(RIGHT_LINES[0])
    assert text.index(LEFT_LINES[0]) < text.index(LEFT_LINES[-1])


def test_table_cells_carry_their_headers_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "layout.pdf"
    make_layout_pdf(path)
    text = load_pdf_pages(path)[0]
    assert "[TABLE: March 31, 2026 | March 31, 2025]" in text
    assert "Revenue | March 31, 2026: 1,23,456.78 | March 31, 2025: (1,234.50)" in text
    assert text.count("70,346.28") == 1
    assert "[/TABLE]" in text


def test_card_labels_stay_next_to_names(tmp_path: Path) -> None:
    path = tmp_path / "cards.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        for column, (name, role) in enumerate(
            [("MR. A ONE", "Chairman"), ("MS. B TWO", "Director"), ("MR. C THREE", "Auditor")]
        ):
            page.insert_text((60 + column * 150, 100), name, fontsize=8)
            page.insert_text((60 + column * 150, 112), role, fontsize=8)
        document.save(path)
    text = load_pdf_pages(path)[0]
    assert "MR. A ONE | Chairman" in text
    assert "MS. B TWO | Director" in text
    assert "MR. C THREE | Auditor" in text


def test_split_table_chunks_keep_header_prefix(tmp_path: Path) -> None:
    path = tmp_path / "layout.pdf"
    make_layout_pdf(path)
    text = load_pdf_pages(path)[0]
    chunks = chunk_page("D1", 1, text, target_tokens=40, overlap_tokens=0)
    inside = [chunk for chunk in chunks if chunk.prefix]
    assert inside
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text
    assert all(chunk.prefix == "[TABLE: March 31, 2026 | March 31, 2025]" for chunk in inside)
    assert chunk_with_prefix(inside[0]).startswith("[TABLE:")
    plain = chunk_page("D1", 1, text, target_tokens=40, overlap_tokens=0, table_header_prefix=False)
    assert all(chunk.prefix == "" for chunk in plain)
