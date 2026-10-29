"""Build the `bb-chunks` JSON record for every chunk cited anywhere in a report."""

from collections.abc import Iterable

from busybee.policy.policy_sections import PolicySection
from busybee.render.links import POLICY_PAGE, report_pdf_href, source_href
from busybee.schema.documents import Document
from busybee.schema.report import Report

POLICY_QUOTE_CHARS = 300


def _policy_records(
    report: Report, sections: Iterable[PolicySection], policy_title: str
) -> dict[str, dict[str, object]]:
    """Return section_id -> chunk record for every policy section a reason cites."""
    by_id = {section.section_id: section for section in sections}
    records: dict[str, dict[str, object]] = {}
    reasons = report.recommendation.key_reasons if report.recommendation else []
    for reason in reasons:
        for citation in reason.policy_citations:
            section = by_id.get(citation.section_id)
            if section is None or citation.section_id in records:
                continue
            records[citation.section_id] = {
                "doc_id": "Policy",
                "doc_title": f"{policy_title} · {section.heading}",
                "page_no": 0,
                "quote": citation.quote or " ".join(section.text.split())[:POLICY_QUOTE_CHARS],
                "href": f"{POLICY_PAGE}#{section.section_id}",
                "pdf_href": "",
            }
    return records


def build_chunk_blob(
    report: Report,
    documents: Iterable[Document] | None = None,
    policy_sections: Iterable[PolicySection] = (),
    policy_title: str = "Bank policy",
) -> dict[str, dict[str, object]]:
    """Return chunk_id -> {doc_id, doc_title, page_no, quote, href, pdf_href}.

    One record per cited chunk; href opens the extracted text view, pdf_href the original PDF page.

    Cited policy sections are keyed by section id (P3) with page_no 0.
    """
    by_doc = {document.doc_id: document for document in documents or report.documents}
    records: dict[str, dict[str, object]] = {}
    for fact in report.facts.values():
        for citation in fact.citations:
            doc_id = citation.doc_id or citation.chunk_id.split(":", 1)[0]
            existing = records.get(citation.chunk_id)
            if existing is None and citation.source == "bank_input":
                records[citation.chunk_id] = {
                    "doc_id": doc_id,
                    "doc_title": "Credit request (bank input)",
                    "page_no": 0,
                    "quote": citation.quote,
                    "href": "",
                    "pdf_href": "",
                }
            elif existing is None:
                document = by_doc.get(doc_id)
                text_href = source_href(citation.chunk_id)
                original = report_pdf_href(document, citation.page_no)
                records[citation.chunk_id] = {
                    "doc_id": doc_id,
                    "doc_title": document.title if document else doc_id,
                    "page_no": citation.page_no,
                    "quote": citation.quote,
                    "href": text_href,
                    "pdf_href": original or "",
                }
            elif not existing["quote"] and citation.quote:
                existing["quote"] = citation.quote
    records.update(_policy_records(report, policy_sections, policy_title))
    return dict(sorted(records.items()))
