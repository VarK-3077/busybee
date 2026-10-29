"""Stable identifier constructors and the chunk-id parser shared by all stages."""

import re

_CHUNK_ID_PATTERN = re.compile(r"D(\d+):p(\d+):c(\d+)")


def make_doc_id(n: int | str) -> str:
    """Return a document id such as D1 from a number or an existing id."""
    if isinstance(n, str):
        return n if n.startswith("D") else f"D{n}"
    return f"D{n}"


def make_chunk_id(doc_no: int | str, page_no: int, index: int) -> str:
    """Return a page-exact chunk id such as D1:p214:c2."""
    return f"{make_doc_id(doc_no)}:p{page_no}:c{index}"


def parse_chunk_id(chunk_id: str) -> tuple[str, int, int]:
    """Return (doc_id, page_no, index) for a chunk id, raising ValueError if malformed."""
    match = _CHUNK_ID_PATTERN.fullmatch(chunk_id)
    if match is None:
        raise ValueError(f"invalid chunk id: {chunk_id!r}")
    doc_no, page_no, index = match.groups()
    return make_doc_id(int(doc_no)), int(page_no), int(index)


def make_fact_id(n: int) -> str:
    """Return a zero-padded fact id such as F012."""
    return f"F{n:03d}"


def make_entry_id(doc_id: str, n: int) -> str:
    """Return a notebook entry id scoped to its document, such as D1:E001."""
    return f"{make_doc_id(doc_id)}:E{n:03d}"


def make_inference_id(n: int) -> str:
    """Return a zero-padded inference id such as I001."""
    return f"I{n:03d}"


def make_concern_id(n: int) -> str:
    """Return a zero-padded concern id such as C001."""
    return f"C{n:03d}"


def make_score_artifact_id(run_id: str, score_id: str) -> str:
    """Return the Lean artifact id for one score within a run."""
    return f"{run_id}:{score_id}"
