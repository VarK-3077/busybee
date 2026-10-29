"""Write and read the ingest corpus files in the workspace."""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from busybee.schema.documents import Chunk, Document, Page
from busybee.schema.io import append_jsonl, read_jsonl, read_models, write_models_atomic


@dataclass(frozen=True)
class Corpus:
    """The loaded corpus plus convenient page and chunk lookups."""

    documents: list[Document]
    chunks: list[Chunk]
    pages_by_doc: dict[str, list[Page]]
    chunks_by_id: dict[str, Chunk]

    def pages(self, doc_id: str) -> list[Page]:
        """Return all pages of one document, or an empty list if unknown."""
        return self.pages_by_doc.get(doc_id, [])

    def page(self, doc_id: str, page_no: int) -> Page | None:
        """Return one 1-based page of a document, or None if absent."""
        for page in self.pages(doc_id):
            if page.page_no == page_no:
                return page
        return None


def chunks_by_id(chunks: Iterable[Chunk]) -> dict[str, Chunk]:
    """Index chunks by their chunk id."""
    return {chunk.chunk_id: chunk for chunk in chunks}


def _write_jsonl_atomic(path: str | Path, models: Iterable[Chunk | Page]) -> None:
    """Write models as JSONL, replacing the target only after the full write succeeds."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text("", encoding="utf-8")
        for model in models:
            append_jsonl(temporary, model)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_corpus(
    workspace_dir: str | Path,
    documents: Iterable[Document],
    pages_by_doc: dict[str, list[Page]],
    chunks: Iterable[Chunk],
) -> None:
    """Write documents.json, one pages/<doc_id>.jsonl per document, and chunks.jsonl."""
    corpus_dir = Path(workspace_dir) / "corpus"
    document_list = list(documents)
    write_models_atomic(corpus_dir / "documents.json", document_list)
    for document in document_list:
        _write_jsonl_atomic(
            corpus_dir / "pages" / f"{document.doc_id}.jsonl",
            pages_by_doc.get(document.doc_id, []),
        )
    _write_jsonl_atomic(corpus_dir / "chunks.jsonl", chunks)


def load_corpus(workspace_dir: str | Path) -> Corpus:
    """Read the corpus written by ingest into a Corpus object."""
    corpus_dir = Path(workspace_dir) / "corpus"
    documents_path = corpus_dir / "documents.json"
    documents = read_models(documents_path, Document) if documents_path.exists() else []
    chunks = read_jsonl(corpus_dir / "chunks.jsonl", Chunk)
    pages_by_doc: dict[str, list[Page]] = {}
    pages_dir = corpus_dir / "pages"
    if pages_dir.exists():
        for path in sorted(pages_dir.glob("*.jsonl")):
            pages_by_doc[path.stem] = read_jsonl(path, Page)
    return Corpus(
        documents=documents,
        chunks=chunks,
        pages_by_doc=pages_by_doc,
        chunks_by_id=chunks_by_id(chunks),
    )
