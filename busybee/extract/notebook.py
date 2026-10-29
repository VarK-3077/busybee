"""Build and maintain the in-memory notebook of candidate facts for a document."""

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from busybee.schema.documents import Chunk
from busybee.schema.facts import (
    Citation,
    DroppedEntry,
    EntryKind,
    FactRecord,
    NotebookEntry,
)
from busybee.schema.ids import make_entry_id

from .prompts import NewEntry, RecordDraft
from .record_category import category_from_metric
from .rescue_citations import rescue_citations
from .sections import record_section
from .templates import statement_from_record

logger = logging.getLogger(__name__)

_ENTRY_NUMBER = re.compile(r":E(\d+)$")


def _next_numbers(existing: Iterable[NotebookEntry]) -> dict[str, int]:
    """Return the highest entry number already used for each document id."""
    numbers: dict[str, int] = {}
    for entry in existing:
        doc_id = entry.doc_id or entry.entry_id.split(":", 1)[0]
        match = _ENTRY_NUMBER.search(entry.entry_id)
        number = int(match.group(1)) if match else numbers.get(doc_id, 0) + 1
        numbers[doc_id] = max(numbers.get(doc_id, 0), number)
    return numbers


Proposal = NewEntry | RecordDraft


def _as_proposal(entry: Proposal | Mapping[str, Any]) -> Proposal:
    """Accept a validated proposal or a plain mapping (a mapping with `metric` is a record)."""
    if isinstance(entry, NewEntry | RecordDraft):
        return entry
    if "metric" in entry and "statement" not in entry:
        return RecordDraft.model_validate(entry)
    return NewEntry.model_validate(entry)


def _fields_of(proposal: Proposal) -> tuple[str, EntryKind, FactRecord | None] | None:
    """(statement, kind, record) of a proposal; None for a record row without a usable value."""
    if isinstance(proposal, NewEntry):
        return proposal.statement, proposal.kind, None
    record = proposal.to_record()
    if record is None:
        return None
    return statement_from_record(record), EntryKind.number, record


def _with_section(
    record: FactRecord, chunk_ids: Sequence[str], chunks_by_id: Mapping[str, Chunk]
) -> FactRecord:
    """The record with the heading path of its table row, when the cited chunks show one."""
    section = record_section(record.metric, record.value, chunk_ids, chunks_by_id)
    return record.model_copy(update={"section": section}) if section else record


def add_entries(
    entries: Iterable[Proposal | Mapping[str, Any]],
    *,
    doc_id: str | None,
    window_no: int,
    chunks_by_id: Mapping[str, Chunk],
    existing: Iterable[NotebookEntry] = (),
    start_index: int | None = None,
    window_chunks: Sequence[Chunk] = (),
) -> tuple[list[NotebookEntry], list[DroppedEntry]]:
    """Turn model proposals into numbered entries, dropping unknown or empty citations.

    Entry numbers continue from `existing`, which lets a document keep unique ids even
    after an earlier entry has been superseded. Entries with at least one valid chunk id
    are kept; unknown ids are removed and logged, and an entry left with no citation is
    returned as a DroppedEntry with stage "extract", unless `rescue_citations` can infer
    its citation from `window_chunks` (the entry is then flagged `citation_inferred`).
    """
    new_entries = [_as_proposal(entry) for entry in entries]
    numbers = _next_numbers(existing)
    if start_index is not None and doc_id is not None:
        numbers[doc_id] = max(numbers.get(doc_id, 0), start_index - 1)

    kept: list[NotebookEntry] = []
    dropped: list[DroppedEntry] = []
    for proposal in new_entries:
        fields = _fields_of(proposal)
        if fields is None:
            logger.warning("record row without metric or value in window %s; skipped", window_no)
            continue
        statement, kind, record = fields
        if record is not None:
            record = _with_section(record, proposal.chunk_ids, chunks_by_id)
            statement = statement_from_record(record)
        citations: list[Citation] = []
        seen_ids: set[str] = set()
        unknown: list[str] = []
        for chunk_id in proposal.chunk_ids:
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                unknown.append(chunk_id)
                logger.warning(
                    "unknown chunk id %s in window %s; dropping citation", chunk_id, window_no
                )
                continue
            citations.append(
                Citation(chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no)
            )

        inferred = False
        if not citations and window_chunks:
            citations = rescue_citations(statement, window_chunks)
            inferred = bool(citations)

        target_doc = doc_id or (citations[0].doc_id if citations else "D0")
        number = numbers.get(target_doc, 0) + 1
        entry = NotebookEntry(
            entry_id=make_entry_id(target_doc, number),
            statement=statement,
            citations=citations,
            category=category_from_metric(record.metric)
            if record is not None
            else proposal.category,
            kind=kind,
            importance=max(1, min(5, proposal.importance)),
            window_no=window_no,
            doc_id=target_doc,
            supersedes=getattr(proposal, "supersedes", None) or None,
            added_by="extract",
            citation_inferred=inferred,
            record=record,
        )
        if not citations:
            reason = "no valid chunk id"
            if unknown:
                reason = f"no valid chunk id (unknown: {', '.join(unknown)})"
            dropped.append(DroppedEntry(entry=entry, reason=reason, stage="extract"))
            continue
        numbers[target_doc] = number
        kept.append(entry)
    return kept, dropped


def _resolve_target(target: str, entry: NotebookEntry, known_ids: set[str]) -> str:
    """Map a bare "E017" reference onto the entry's own document id when that id exists."""
    if target in known_ids:
        return target
    prefixed = f"{entry.doc_id or entry.entry_id.split(':', 1)[0]}:{target.lstrip(':')}"
    return prefixed if prefixed in known_ids else target


def apply_supersedes(
    entries: Iterable[NotebookEntry],
    *,
    check: Iterable[NotebookEntry] | None = None,
    history_ids: Iterable[str] = (),
) -> list[NotebookEntry]:
    """Remove entries replaced by a later entry, keeping the supersedes link for audit.

    Only the links of `check` (default: all entries) are evaluated, so an entry that was
    already applied in an earlier window is not re-examined. A target that is no longer
    active but appears in `history_ids` was removed earlier and is skipped silently; any
    other target is logged once as unknown with the offending id.
    """
    ordered = list(entries)
    active_ids = {entry.entry_id for entry in ordered}
    past_ids = set(history_ids)
    superseded_ids: set[str] = set()
    for entry in ordered if check is None else check:
        if not entry.supersedes:
            continue
        target = _resolve_target(entry.supersedes.strip(), entry, active_ids | past_ids)
        if target == entry.entry_id:
            continue
        if target in active_ids:
            superseded_ids.add(target)
        elif target not in past_ids:
            logger.warning("entry %s supersedes unknown entry %s", entry.entry_id, target)
    return [entry for entry in ordered if entry.entry_id not in superseded_ids]


def renumber(
    entries: Iterable[NotebookEntry],
    doc_id: str | None = None,
) -> list[NotebookEntry]:
    """Assign fresh per-document sequential ids in the current order."""
    counters: dict[str, int] = {}
    renumbered: list[NotebookEntry] = []
    for entry in entries:
        target_doc = doc_id or entry.doc_id or entry.entry_id.split(":", 1)[0]
        number = counters.get(target_doc, 0) + 1
        counters[target_doc] = number
        renumbered.append(
            entry.model_copy(
                update={"entry_id": make_entry_id(target_doc, number), "doc_id": target_doc}
            )
        )
    return renumbered


def merge_notebooks(
    per_doc: Iterable[Iterable[NotebookEntry]] | Mapping[str, Iterable[NotebookEntry]],
) -> list[NotebookEntry]:
    """Concatenate per-document notebooks, preserving document and entry order."""
    groups = per_doc.values() if isinstance(per_doc, Mapping) else per_doc
    return [entry for group in groups for entry in group]
