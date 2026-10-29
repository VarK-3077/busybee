"""Assign stable D1..Dn ids to documents in kind-priority then filename order."""

from busybee.ingest.kinds import sort_key
from busybee.schema.documents import Document
from busybee.schema.ids import make_doc_id


def _name(document: Document) -> str:
    """Return the filename used as the deterministic tie-breaker."""
    return document.source_path or document.title


def order_documents(documents: list[Document]) -> list[Document]:
    """Return documents sorted by kind priority and then filename."""
    return sorted(documents, key=lambda document: sort_key(document.kind, _name(document)))


def assign_doc_ids(documents: list[Document]) -> list[Document]:
    """Return ordered documents with doc ids D1, D2, ... assigned."""
    ordered = order_documents(documents)
    return [
        document.model_copy(update={"doc_id": make_doc_id(number)})
        for number, document in enumerate(ordered, start=1)
    ]
