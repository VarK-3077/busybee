"""Document, page, chunk, and scored-chunk models produced by ingest and index."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentKind(StrEnum):
    """The document types the pipeline recognises, in reading-priority order."""

    annual_report = "annual_report"
    drhp = "drhp"
    financial_statements = "financial_statements"
    rating_rationale = "rating_rationale"
    covenant = "covenant"
    bank_statement = "bank_statement"
    news = "news"
    other = "other"


class Document(BaseModel):
    """A source document in the pack."""

    doc_id: str
    title: str
    kind: DocumentKind = DocumentKind.other
    source_path: str = ""
    sha256: str = ""
    num_pages: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Page(BaseModel):
    """One 1-based page of extracted text."""

    doc_id: str
    page_no: int
    text: str = ""


class Chunk(BaseModel):
    """A page-bounded text chunk with offsets into the page text."""

    chunk_id: str
    doc_id: str
    page_no: int
    index_in_page: int
    text: str = ""
    char_start: int = 0
    char_end: int = 0
    prefix: str = ""


class ScoredChunk(BaseModel):
    """A chunk returned by vector search together with its similarity score."""

    chunk: Chunk
    score: float
