"""Infer a document kind from its filename and first page, and order kinds for reading."""

import re
from pathlib import Path

from busybee.schema.documents import DocumentKind

KIND_PRIORITY: list[DocumentKind] = [
    DocumentKind.financial_statements,
    DocumentKind.annual_report,
    DocumentKind.drhp,
    DocumentKind.rating_rationale,
    DocumentKind.covenant,
    DocumentKind.bank_statement,
    DocumentKind.news,
    DocumentKind.other,
]

_KEYWORDS: dict[DocumentKind, tuple[str, ...]] = {
    DocumentKind.financial_statements: (
        "financial statements",
        "financial statement",
        "balance sheet",
        "profit and loss",
        "cash flow statement",
        "statement of assets and liabilities",
        "audited financial",
    ),
    DocumentKind.annual_report: (
        "annual report",
        "annual accounts",
        "chairman",
        "directors report",
        "board report",
        "management discussion",
    ),
    DocumentKind.drhp: (
        "drhp",
        "draft red herring prospectus",
        "red herring prospectus",
        "prospectus",
        "rhp",
    ),
    DocumentKind.rating_rationale: (
        "rating rationale",
        "credit rating",
        "rating action",
        "rating outlook",
        "reaffirmed",
        "rationale",
        "crisil",
        "icra",
        "care ratings",
        "india ratings",
    ),
    DocumentKind.covenant: (
        "covenant",
        "financial covenants",
        "dscr",
        "debt service coverage",
        "sanction letter",
    ),
    DocumentKind.bank_statement: (
        "bank statement",
        "account conduct",
        "cash credit",
        "bank summary",
        "operating account",
        "statement of account",
    ),
    DocumentKind.news: (
        "news",
        "press release",
        "media release",
        "reported",
        "said on",
        "quarter ended",
        "announced",
        "earnings call",
    ),
}

_KIND_ORDER = {kind: index for index, kind in enumerate(KIND_PRIORITY)}


def _normalise(text: str) -> str:
    """Lowercase text and turn punctuation and separators into single spaces."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def infer_kind(filename: str, first_page_text: str) -> DocumentKind:
    """Return the most likely kind, weighting filename evidence above page text."""
    name = _normalise(Path(filename).name)
    body = _normalise(first_page_text)
    best_kind = DocumentKind.other
    best_score = 0
    for kind in KIND_PRIORITY:
        score = 0
        for keyword in _KEYWORDS.get(kind, ()):
            needle = _normalise(keyword)
            if not needle:
                continue
            if needle in name:
                score += 5
            if needle in body:
                score += 1
        if score > best_score:
            best_kind = kind
            best_score = score
    return best_kind


def sort_key(kind: DocumentKind | str, name: str) -> tuple[int, str]:
    """Return the deterministic reading order key: kind priority, then filename."""
    document_kind = kind if isinstance(kind, DocumentKind) else DocumentKind(kind)
    return (_KIND_ORDER[document_kind], Path(name).name.lower())
