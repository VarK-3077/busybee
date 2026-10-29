"""Skip boilerplate pages of long documents before windowing, by the section title on the page.

An annual report carries tens of pages the credit decision never uses: the AGM notice with its
explanatory statement and director profiles, the CSR report, the business responsibility and
sustainability report, the corporate governance report, the secretarial audit form MR-3, the
route map, proxy form and attendance slip. `skipped_pages` walks a document's pages in order
and keeps a skip run open from a page whose first three lines (eight for the notice titles)
carry one of `BOILERPLATE_TITLES` (regular expressions matched at the start of a line,
case-insensitive; `BUSYBEE_BOILERPLATE_TITLES` appends more, separated by `;`) until a page
that is not boilerplate: a hard stop is a financial-statement, auditor's report, management
discussion or directors' report title, a soft stop (not for the AGM notice, whose annexures
belong to it) is the next annexure to the directors' report or a Form AOC. A run
is also cut after `MAX_RUN_PAGES`. A page holding a financial statement, notes to accounts, the
auditor's report or the MD&A is never skipped and always ends the run. `drop_boilerplate`
removes the chunks of skipped pages for the extract stage only (index and verify still see
them), logs how many pages and chunks went, and `BUSYBEE_SKIP_BOILERPLATE=0` turns it off.
"""

import logging
import os
import re
from collections.abc import Mapping, Sequence

from busybee.schema.documents import Chunk, Document, DocumentKind

logger = logging.getLogger(__name__)

TITLE_LINES = 8
HEADING_LINES = 3
MAX_RUN_PAGES = 60
MAX_PROTECTED_LINE_CHARS = 80
SKIPPED_KINDS = frozenset({DocumentKind.annual_report, DocumentKind.drhp})

NOTICE_TITLES: tuple[str, ...] = (
    r"^n\s*o\s*t\s*i\s*c\s*e$",
    r"notice is hereby given",
    r"^notice of (the )?[\w\s-]{0,40}general meeting",
    r"route map",
    r"proxy form|form no\.? mgt-?11",
    r"attendance slip",
    r"profile of directors|brief (resume|profile|curriculum vitae)",
)
BOILERPLATE_TITLES: tuple[str, ...] = (
    *NOTICE_TITLES,
    r"annual report on corporate social responsibility",
    r"^corporate social responsibility( \(csr\))?( report)?$",
    r"business responsibility (and|&) sustainability report",
    r"report on corporate governance|^corporate governance report",
    r"secretarial audit report|form (no\.? )?mr-?3",
)
HARD_STOP_TITLES: tuple[str, ...] = (
    r"^management discussion",
    r"^(consolidated )?independent auditor",
    r"^(consolidated |standalone )?(balance sheet|statement of (profit|assets)|cash flow)",
    r"^notes (to|forming|\((standalone|consolidated)\))",
    r"^(directors|board)[’']?s?[’']? report",
)
SOFT_STOP_TITLES: tuple[str, ...] = (r"^form aoc",)
_ANNEXURE_TO_REPORT = re.compile(r"^annexure[\s\-–]*\w*\s*\n\s*to the (directors|board)", re.I)
_FINANCIAL_STATEMENT_LINE = re.compile(
    r"^(consolidated |standalone )?(balance sheet|statement of profit and loss|"
    r"cash flow statement|statement of changes in equity)\b|^notes to (the )?(consolidated |"
    r"standalone )?(financial statements|accounts)\b|^independent auditor|^management discussion",
    re.I,
)
_NOTICE = re.compile("|".join(NOTICE_TITLES), re.I)


def configured_titles(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The default titles plus any `;`-separated regexes in BUSYBEE_BOILERPLATE_TITLES."""
    env = os.environ if environ is None else environ
    extra = tuple(part.strip() for part in env.get("BUSYBEE_BOILERPLATE_TITLES", "").split(";"))
    return (*BOILERPLATE_TITLES, *(part for part in extra if part))


def enabled(environ: Mapping[str, str] | None = None) -> bool:
    """False only when BUSYBEE_SKIP_BOILERPLATE is set to 0, false or off."""
    env = os.environ if environ is None else environ
    return env.get("BUSYBEE_SKIP_BOILERPLATE", "1").strip().lower() not in {"0", "false", "off"}


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _any_line(patterns: Sequence[str], lines: Sequence[str]) -> bool:
    compiled = [re.compile(r"[\W\d_]*(?:" + pattern + ")", re.IGNORECASE) for pattern in patterns]
    return any(rx.match(line) for rx in compiled for line in lines)


def _is_protected(top: Sequence[str], all_lines: Sequence[str]) -> bool:
    if _any_line(HARD_STOP_TITLES, top):
        return True
    return any(
        len(line) <= MAX_PROTECTED_LINE_CHARS and _FINANCIAL_STATEMENT_LINE.search(line)
        for line in all_lines
    )


def _page_texts(chunks: Sequence[Chunk]) -> dict[int, str]:
    pages: dict[int, list[Chunk]] = {}
    for chunk in chunks:
        pages.setdefault(chunk.page_no, []).append(chunk)
    return {
        page_no: "\n".join(c.text for c in sorted(items, key=lambda c: c.index_in_page))
        for page_no, items in sorted(pages.items())
    }


def skipped_pages(chunks: Sequence[Chunk], titles: Sequence[str] | None = None) -> list[int]:
    """Page numbers of one document that are boilerplate, in page order."""
    start_titles = BOILERPLATE_TITLES if titles is None else tuple(titles)
    skipped: list[int] = []
    run_soft: bool | None = None
    run_pages = 0
    for page_no, text in _page_texts(chunks).items():
        all_lines = _lines(text)
        top = all_lines[:TITLE_LINES]
        if _is_protected(top, all_lines):
            run_soft = None
            continue
        if _any_line(start_titles, top[:HEADING_LINES]) or _any_line(NOTICE_TITLES, top):
            run_soft = _NOTICE.search("\n".join(top)) is None
            run_pages = 0
        elif run_soft is not None and (
            _any_line(SOFT_STOP_TITLES, top) or _ANNEXURE_TO_REPORT.search("\n".join(top[:3]))
        ):
            if run_soft:
                run_soft = None
        if run_soft is None or run_pages >= MAX_RUN_PAGES:
            run_soft = None
            continue
        run_pages += 1
        skipped.append(page_no)
    return skipped


def drop_boilerplate(
    documents: Sequence[Document],
    chunks_by_doc: Mapping[str, Sequence[Chunk]],
    titles: Sequence[str] | None = None,
) -> tuple[dict[str, list[Chunk]], dict[str, list[int]]]:
    """Chunks per document without boilerplate pages, and the skipped page numbers per document."""
    kept: dict[str, list[Chunk]] = {}
    skipped: dict[str, list[int]] = {}
    kinds = {document.doc_id: document.kind for document in documents}
    for doc_id, chunks in chunks_by_doc.items():
        pages = skipped_pages(chunks, titles) if kinds.get(doc_id) in SKIPPED_KINDS else []
        if pages:
            skipped[doc_id] = pages
        dropped = set(pages)
        kept[doc_id] = [chunk for chunk in chunks if chunk.page_no not in dropped]
    page_count = sum(len(pages) for pages in skipped.values())
    chunk_count = sum(len(chunks_by_doc[d]) - len(kept[d]) for d in skipped)
    logger.info(
        "skipped %d boilerplate pages (%d chunks) before extraction", page_count, chunk_count
    )
    return kept, skipped
