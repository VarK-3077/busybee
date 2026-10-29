"""Result models of one question: citations, checked sentences and the whole answer."""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """One retrieved chunk a sentence relies on, with the page where it sits."""

    chunk_id: str
    doc_id: str
    page_no: int
    pdf_href: str | None = None


class CheckedSentence(BaseModel):
    """An answer sentence with its citations, verdict and the reason when not supported."""

    text: str
    citations: list[Citation] = Field(default_factory=list)
    supported: bool = False
    note: str = ""


class Answer(BaseModel):
    """The verified answer to one question; `answered` is False when nothing relevant was found."""

    question: str
    answered: bool
    sentences: list[CheckedSentence] = Field(default_factory=list)
    message: str = ""
