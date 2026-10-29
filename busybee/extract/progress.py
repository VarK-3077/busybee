"""Crash-safe progress file of the extract stage: `extract_progress.jsonl`.

When a segment's rolling notebook is finished, its entries and dropped list are appended as one
JSON line keyed by (doc_id, segment index) with a fingerprint of the segment's chunks and the
segment count. On a restart `load_segments` returns the finished segments whose fingerprint
still matches, so only unfinished segments call the LLM again; a truncated last line from a
crash is ignored. The stage deletes the file once notebook.json is written.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from busybee.schema.documents import Chunk
from busybee.schema.facts import DroppedEntry, NotebookEntry
from busybee.schema.io import append_jsonl

PROGRESS_FILE = "extract_progress.jsonl"


class SegmentRecord(BaseModel):
    """One finished segment notebook."""

    doc_id: str
    segment: int
    fingerprint: str
    entries: list[NotebookEntry]
    dropped: list[DroppedEntry]


def segment_fingerprint(windows: Sequence[Sequence[Chunk]], count: int) -> str:
    """Hash the segment count and the chunk ids of the segment's windows."""
    text = f"{count}|" + "|".join(chunk.chunk_id for window in windows for chunk in window)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def record_segment(
    path: Path,
    doc_id: str,
    segment: int,
    fingerprint: str,
    entries: list[NotebookEntry],
    dropped: list[DroppedEntry],
) -> None:
    """Append one finished segment."""
    append_jsonl(
        path,
        SegmentRecord(
            doc_id=doc_id,
            segment=segment,
            fingerprint=fingerprint,
            entries=entries,
            dropped=dropped,
        ),
    )


def load_segments(path: Path) -> dict[tuple[str, int], SegmentRecord]:
    """Return the finished segments by (doc_id, segment index); the latest line wins."""
    if not path.exists():
        return {}
    records: dict[tuple[str, int], SegmentRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = SegmentRecord.model_validate_json(line)
        except ValidationError:
            continue
        records[(record.doc_id, record.segment)] = record
    return records
