"""Order documents for reading, using the same kind priority as the ingest stage."""

from collections.abc import Iterable
from pathlib import Path

from busybee.ingest.kinds import KIND_PRIORITY
from busybee.schema.documents import Document, DocumentKind

_PRIORITY: dict[DocumentKind, int] = {kind: index for index, kind in enumerate(KIND_PRIORITY)}


def document_order_key(document: Document) -> tuple[int, str]:
    """Return the deterministic reading key: kind priority, then filename."""
    name = Path(document.source_path or document.title).name.lower()
    return (_PRIORITY.get(document.kind, len(_PRIORITY)), name)


def order_documents(documents: Iterable[Document]) -> list[Document]:
    """Return the documents in the order the extractor should read them."""
    return sorted(documents, key=document_order_key)
