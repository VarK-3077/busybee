"""Tests for numbering, citation building, supersedes, and notebook merging."""

import logging

from busybee.extract.notebook import add_entries, apply_supersedes, merge_notebooks
from busybee.extract.prompts import NewEntry
from busybee.schema.documents import Chunk
from busybee.schema.facts import (
    Citation,
    EntryKind,
    FactCategory,
    NotebookEntry,
)

CHUNK = Chunk(
    chunk_id="D1:p1:c0",
    doc_id="D1",
    page_no=1,
    index_in_page=0,
    text="Revenue was INR 931.2 crore in FY25.",
)


def notebook_entry(entry_id: str, doc_id: str, statement: str) -> NotebookEntry:
    return NotebookEntry(
        entry_id=entry_id,
        statement=statement,
        citations=[Citation(chunk_id="D1:p1:c0", doc_id=doc_id, page_no=1)],
        category=FactCategory.revenue,
        kind=EntryKind.number,
        doc_id=doc_id,
    )


def test_add_entries_numbers_from_history_and_builds_citations() -> None:
    existing = [notebook_entry("D1:E003", "D1", "An earlier fact.")]
    proposal = NewEntry(
        statement="Revenue was INR 931.2 crore in FY25.",
        chunk_ids=["D1:p1:c0", "D1:p9:c9", "D1:p1:c0"],
        category=FactCategory.revenue,
        kind=EntryKind.number,
        importance=9,
    )

    kept, dropped = add_entries(
        [proposal],
        doc_id="D1",
        window_no=2,
        chunks_by_id={CHUNK.chunk_id: CHUNK},
        existing=existing,
    )

    assert dropped == []
    assert len(kept) == 1
    entry = kept[0]
    assert entry.entry_id == "D1:E004"
    assert entry.window_no == 2
    assert entry.doc_id == "D1"
    assert entry.importance == 5
    assert entry.added_by == "extract"
    assert entry.citations == [Citation(chunk_id="D1:p1:c0", doc_id="D1", page_no=1)]
    assert entry.citations[0].quote == ""


def test_unknown_chunk_ids_are_dropped_and_logged(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="busybee.extract.notebook")
    proposal = NewEntry(
        statement="A fact with a bad citation.",
        chunk_ids=["D1:p1:c0", "D9:p9:c9"],
        category=FactCategory.other,
    )

    kept, dropped = add_entries(
        [proposal],
        doc_id="D1",
        window_no=1,
        chunks_by_id={CHUNK.chunk_id: CHUNK},
    )

    assert len(kept) == 1
    assert [citation.chunk_id for citation in kept[0].citations] == ["D1:p1:c0"]
    assert "D9:p9:c9" in caplog.text
    assert dropped == []


def test_an_entry_with_no_valid_chunk_id_is_discarded() -> None:
    proposal = NewEntry(
        statement="A fact with no usable citation.",
        chunk_ids=["D9:p9:c9"],
        category=FactCategory.other,
    )

    kept, dropped = add_entries(
        [proposal],
        doc_id="D1",
        window_no=1,
        chunks_by_id={CHUNK.chunk_id: CHUNK},
    )

    assert kept == []
    assert len(dropped) == 1
    assert dropped[0].stage == "extract"
    assert dropped[0].entry.statement == "A fact with no usable citation."
    assert "D9:p9:c9" in dropped[0].reason


def test_apply_supersedes_removes_the_older_entry() -> None:
    older = notebook_entry("D1:E001", "D1", "Revenue was 931.2 crore.")
    newer = notebook_entry("D1:E002", "D1", "Revenue was restated to 941.0 crore.")
    newer = newer.model_copy(update={"supersedes": older.entry_id})

    assert apply_supersedes([older, newer]) == [newer]


def test_apply_supersedes_ignores_self_and_unknown_targets() -> None:
    entry = notebook_entry("D1:E001", "D1", "Revenue was 931.2 crore.")
    entry = entry.model_copy(update={"supersedes": entry.entry_id})
    other = notebook_entry("D1:E002", "D1", "Cash was 20 crore.")
    other = other.model_copy(update={"supersedes": "D1:E099"})

    assert apply_supersedes([entry, other]) == [entry, other]


def test_merge_notebooks_preserves_document_and_entry_order() -> None:
    d1_first = notebook_entry("D1:E001", "D1", "First fact.")
    d1_second = notebook_entry("D1:E002", "D1", "Second fact.")
    d2_first = notebook_entry("D2:E001", "D2", "Third fact.")

    merged = merge_notebooks([[d1_first, d1_second], [d2_first]])

    assert merged == [d1_first, d1_second, d2_first]


def test_apply_supersedes_warns_once_and_not_for_already_applied_links(caplog) -> None:
    older = notebook_entry("D1:E001", "D1", "Revenue was 931.2 crore.")
    newer = notebook_entry("D1:E002", "D1", "Revenue was restated to 941.0 crore.")
    newer = newer.model_copy(update={"supersedes": older.entry_id})
    bogus = notebook_entry("D1:E003", "D1", "Cash was 20 crore.")
    bogus = bogus.model_copy(update={"supersedes": "D1:E099"})

    with caplog.at_level(logging.WARNING):
        active = apply_supersedes([older, newer, bogus], check=[newer, bogus], history_ids=[])
        apply_supersedes(active, check=[], history_ids=["D1:E001"])
        apply_supersedes(active, check=[newer], history_ids=["D1:E001"])

    assert active == [newer, bogus]
    assert [r.getMessage() for r in caplog.records].count(
        "entry D1:E003 supersedes unknown entry D1:E099"
    ) == 1
    assert len(caplog.records) == 1


def test_apply_supersedes_accepts_bare_entry_number() -> None:
    older = notebook_entry("D1:E017", "D1", "Revenue was 931.2 crore.")
    newer = notebook_entry("D1:E023", "D1", "Revenue was restated.")
    newer = newer.model_copy(update={"supersedes": "E017"})

    assert apply_supersedes([older, newer]) == [newer]


def _chunk(index: int, text: str) -> Chunk:
    return Chunk(chunk_id=f"D1:p1:c{index}", doc_id="D1", page_no=1, index_in_page=index, text=text)


WINDOW = [
    _chunk(0, "Revenue was INR 931.2 crore in FY25 and PAT was INR 41.5 crore."),
    _chunk(1, "The board met on several dates during the year."),
    _chunk(2, "Rating history: CRISIL A on 12 March 2024."),
]


def _add(statement: str, window: list[Chunk]) -> tuple[list[NotebookEntry], list]:
    return add_entries(
        [NewEntry(statement=statement, chunk_ids=[])],
        doc_id="D1",
        window_no=1,
        chunks_by_id={c.chunk_id: c for c in window},
        window_chunks=window,
    )


def test_rescue_attaches_chunk_matching_all_numbers() -> None:
    kept, dropped = _add("Revenue was INR 931.2 crore in FY25.", WINDOW)
    assert not dropped
    assert [c.chunk_id for c in kept[0].citations] == ["D1:p1:c0"]
    assert kept[0].citation_inferred


def test_rescue_skips_when_more_than_two_chunks_match() -> None:
    window = [_chunk(i, "Revenue was INR 931.2 crore in FY25.") for i in range(3)]
    kept, dropped = _add("Revenue was INR 931.2 crore in FY25.", window)
    assert not kept
    assert dropped[0].reason == "no valid chunk id"


def test_rescue_skips_when_no_numbers_and_no_overlap() -> None:
    kept, dropped = _add("The promoter pledged shares to lenders.", WINDOW)
    assert not kept and len(dropped) == 1


def test_rescue_numberless_entry_uses_single_best_overlap() -> None:
    window = [
        _chunk(0, "The board of directors met on several dates during the year to review."),
        _chunk(1, "Unrelated text about plant capacity."),
    ]
    kept, _ = _add("The board of directors met on several dates.", window)
    assert kept[0].citation_inferred
    assert kept[0].citations[0].chunk_id == "D1:p1:c0"


def test_no_rescue_without_window_chunks() -> None:
    kept, dropped = add_entries(
        [NewEntry(statement="Revenue was INR 931.2 crore in FY25.", chunk_ids=[])],
        doc_id="D1",
        window_no=1,
        chunks_by_id={},
    )
    assert not kept and dropped
