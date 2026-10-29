"""Tests for format-specific page loading and dispatch."""

from pathlib import Path

import pymupdf
import pytest

from busybee.ingest.loaders.dispatch import load_pages


def make_three_page_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        for number in range(1, 4):
            page = document.new_page()
            page.insert_text((72, 72), f"Page {number} revenue {100 + number} crore.")
        document.save(path)


def test_pdf_loader_returns_one_page_per_pdf_page(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    make_three_page_pdf(path)
    pages = load_pages(path)
    assert len(pages) == 3
    assert "Page 1" in pages[0]
    assert "Page 2" in pages[1]
    assert "Page 3" in pages[2]
    assert "103" in pages[2]


def test_markdown_splits_on_page_markers(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text(
        "# One\n\nAlpha\n\n<!-- page -->\n\n# Two\n\nBeta\n\n<!-- PAGE -->\n\nGamma",
        encoding="utf-8",
    )
    pages = load_pages(path)
    assert len(pages) == 3
    assert pages[0].startswith("# One")
    assert pages[1].startswith("# Two")
    assert pages[2] == "Gamma"


def test_markdown_without_markers_is_one_page(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Title\n\nOnly page.", encoding="utf-8")
    assert load_pages(path) == ["# Title\n\nOnly page."]


def test_plain_text_splits_on_form_feed(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("First\fSecond\fThird", encoding="utf-8")
    assert load_pages(path) == ["First", "Second", "Third"]


def test_html_loader_strips_tags_scripts_and_styles(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><style>.bad { color: red; }</style>"
        "<script>window.bad = true;</script></head>"
        "<body><h1>Acme Textiles</h1><p>Revenue was 10 crore.</p></body></html>",
        encoding="utf-8",
    )
    pages = load_pages(path)
    assert len(pages) == 1
    assert "Acme Textiles" in pages[0]
    assert "Revenue was 10 crore." in pages[0]
    assert "window.bad" not in pages[0]
    assert ".bad" not in pages[0]


def test_dispatch_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("a,b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        load_pages(path)
