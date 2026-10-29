"""Tests for kind inference, priority ordering, and manifest overrides."""

from pathlib import Path

from busybee.ingest.kinds import KIND_PRIORITY, infer_kind, sort_key
from busybee.ingest.manifest import load_manifest
from busybee.schema.documents import DocumentKind


def test_infer_kind_from_filename() -> None:
    assert infer_kind("annual_report_fy25.pdf", "") is DocumentKind.annual_report
    assert infer_kind("financial_statements.pdf", "") is DocumentKind.financial_statements
    assert infer_kind("drhp_2022.pdf", "") is DocumentKind.drhp
    assert infer_kind("crisil_rationale.html", "") is DocumentKind.rating_rationale
    assert infer_kind("covenant_sheet.md", "") is DocumentKind.covenant
    assert infer_kind("bank_statement_summary.md", "") is DocumentKind.bank_statement
    assert infer_kind("news_q1.md", "") is DocumentKind.news


def test_infer_kind_falls_back_to_first_page_keywords() -> None:
    assert infer_kind("document.txt", "Draft Red Herring Prospectus") is DocumentKind.drhp
    assert infer_kind("document.txt", "Financial Covenants and DSCR") is DocumentKind.covenant
    assert infer_kind("document.txt", "Some unrelated text") is DocumentKind.other


def test_kind_priority_matches_architecture_order() -> None:
    assert KIND_PRIORITY == [
        DocumentKind.financial_statements,
        DocumentKind.annual_report,
        DocumentKind.drhp,
        DocumentKind.rating_rationale,
        DocumentKind.covenant,
        DocumentKind.bank_statement,
        DocumentKind.news,
        DocumentKind.other,
    ]


def test_sort_key_uses_kind_then_filename() -> None:
    assert sort_key(DocumentKind.annual_report, "z.pdf") < sort_key(DocumentKind.covenant, "a.pdf")
    assert sort_key(DocumentKind.news, "a.md") < sort_key(DocumentKind.news, "b.md")


def test_manifest_missing_returns_empty(tmp_path: Path) -> None:
    assert load_manifest(tmp_path) == {}


def test_manifest_reads_title_and_kind(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"news.md": {"title": "Custom", "kind": "covenant"}}', encoding="utf-8"
    )
    assert load_manifest(tmp_path) == {"news.md": {"title": "Custom", "kind": "covenant"}}
