"""Build bundle-relative URLs for source chunks, original PDFs, and Lean artifacts."""

import re
from pathlib import Path
from urllib.parse import quote

from busybee.schema.documents import Document
from busybee.schema.ids import parse_chunk_id

POLICY_PAGE = "policy.html"


def source_href(chunk_id: str) -> str:
    """Return the report-relative URL of a chunk anchor on its source page."""
    try:
        doc_id, _, _ = parse_chunk_id(chunk_id)
    except ValueError:
        doc_id = chunk_id.split(":", 1)[0]
    return f"sources/{doc_id}.html#{chunk_id}"


def source_page_href(doc_id: str) -> str:
    """Return the report-relative URL of one document's source page."""
    return f"sources/{doc_id}.html"


def original_filename(document: Document) -> str:
    """Return the filename under originals/ for a document's original file."""
    if document.source_path:
        return Path(document.source_path).name
    return f"{document.doc_id}.pdf"


def pdf_href(document: Document, page_no: int, prefix: str = "../") -> str:
    """Return a URL that opens the original at a page; the default prefix suits sources/*.html."""
    filename = quote(original_filename(document))
    return f"{prefix}originals/{filename}#page={page_no}"


def report_pdf_href(document: Document | None, page_no: int) -> str | None:
    """Return the index-relative URL of a PDF original at a page, or None when not a PDF."""
    if document is None or not document.source_path or page_no < 1:
        return None
    if Path(document.source_path).suffix.lower() != ".pdf":
        return None
    return pdf_href(document, page_no, prefix="")


def artifact_slug(artifact_id: str) -> str:
    """Return a filesystem-safe artifact name without losing its identity."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", artifact_id).strip("-")
    return slug or "artifact"


def lean_anchor_id(artifact_id: str) -> str:
    """Return the id of the Lean section that a #bb-lean href points at."""
    return f"lean-{artifact_slug(artifact_id)}"


def lean_href(artifact_id: str) -> str:
    """Return the report-relative URL of a Lean artifact page and its section."""
    return f"lean/{artifact_slug(artifact_id)}.html#{lean_anchor_id(artifact_id)}"
