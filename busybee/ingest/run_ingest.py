"""Run the ingest stage: load a document pack and write the page-exact corpus."""

from pathlib import Path

from busybee.ingest.chunker import chunk_page
from busybee.ingest.corpus_store import write_corpus
from busybee.ingest.hashing import sha256_file
from busybee.ingest.kinds import infer_kind
from busybee.ingest.loaders.dispatch import SUPPORTED_EXTENSIONS, load_pages
from busybee.ingest.manifest import load_manifest
from busybee.ingest.ordering import assign_doc_ids
from busybee.schema.documents import Document, DocumentKind, Page


def _kind_from_override(filename: str, first_page: str, override: str | None) -> DocumentKind:
    """Return the manifest kind when valid, otherwise infer it from the document."""
    if override:
        try:
            return DocumentKind(override)
        except ValueError:
            pass
    return infer_kind(filename, first_page)


async def run_ingest(docs_dir: str | Path, workspace_dir: str | Path) -> list[Document]:
    """Load every supported document, assign ids, chunk pages, and write the corpus."""
    source_dir = Path(docs_dir)
    manifest = load_manifest(source_dir)
    paths = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    records: list[tuple[Document, list[str]]] = []
    for path in paths:
        pages = load_pages(path)
        first_page = pages[0] if pages else ""
        override = manifest.get(path.name, {})
        kind = _kind_from_override(path.name, first_page, override.get("kind"))
        title = override.get("title") or path.stem
        document = Document(
            doc_id="",
            title=title,
            kind=kind,
            source_path=str(path),
            sha256=sha256_file(path),
            num_pages=len(pages),
            metadata={"filename": path.name},
        )
        records.append((document, pages))

    pages_by_source = {document.source_path: pages for document, pages in records}
    documents = assign_doc_ids([document for document, _ in records])
    pages_by_doc: dict[str, list[Page]] = {}
    chunks = []
    for document in documents:
        page_models = [
            Page(doc_id=document.doc_id, page_no=page_no, text=text)
            for page_no, text in enumerate(pages_by_source[document.source_path], start=1)
        ]
        pages_by_doc[document.doc_id] = page_models
        for page in page_models:
            chunks.extend(chunk_page(document.doc_id, page.page_no, page.text))

    write_corpus(workspace_dir, documents, pages_by_doc, chunks)
    return documents
