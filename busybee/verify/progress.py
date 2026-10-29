"""Crash-safe progress file of the verify stage: `verify_progress.jsonl`.

Every notebook entry's outcome (a `VerifiedFact` or a `DroppedEntry`) is appended as one JSON
line the moment it is known, keyed by `entry_id` together with a fingerprint of the entry. On a
restart `load_progress` returns the outcomes whose fingerprint still matches the current entry,
so finished entries are never sent to the LLM again; a truncated last line from a crash is
ignored. The stage deletes the file once its real outputs are written.

An entry whose LLM or classifier call still fails after the retry budget is dropped with stage
`verify.error` and is deliberately not written here, so a re-run tries it again. The stage only
fails when more than `MAX_ERROR_FRACTION` (20%) of the work items errored (`too_many_errors`),
which means a systemic outage rather than one unlucky call.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from busybee.schema.facts import DroppedEntry, NotebookEntry, VerifiedFact
from busybee.schema.io import append_jsonl

PROGRESS_FILE = "verify_progress.jsonl"
MAX_ERROR_FRACTION = 0.2


def too_many_errors(failed: int, total: int) -> bool:
    """True when the failed share of total work items exceeds MAX_ERROR_FRACTION."""
    return total > 0 and failed / total > MAX_ERROR_FRACTION


class ProgressRecord(BaseModel):
    """One finished entry: exactly one of `fact` and `dropped` is set."""

    entry_id: str
    fingerprint: str
    fact: VerifiedFact | None = None
    dropped: DroppedEntry | None = None


def entry_fingerprint(entry: NotebookEntry) -> str:
    """Return a short hash of the entry so stale progress from another notebook is not reused."""
    return hashlib.sha256(entry.model_dump_json().encode("utf-8")).hexdigest()[:16]


def record_outcome(
    path: Path,
    entry: NotebookEntry,
    *,
    fact: VerifiedFact | None = None,
    dropped: DroppedEntry | None = None,
) -> None:
    """Append the outcome of one entry to the progress file."""
    append_jsonl(
        path,
        ProgressRecord(
            entry_id=entry.entry_id,
            fingerprint=entry_fingerprint(entry),
            fact=fact,
            dropped=dropped,
        ),
    )


def load_progress(path: Path, entries: Sequence[NotebookEntry]) -> dict[str, ProgressRecord]:
    """Return the recorded outcomes by entry_id that still match the given entries."""
    if not path.exists():
        return {}
    wanted = {entry.entry_id: entry_fingerprint(entry) for entry in entries}
    records: dict[str, ProgressRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = ProgressRecord.model_validate_json(line)
        except ValidationError:
            continue
        if wanted.get(record.entry_id) == record.fingerprint:
            records[record.entry_id] = record
    return records
