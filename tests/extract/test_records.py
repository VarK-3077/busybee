"""Records in the extractor: prompt addendum, response model, entries built by code."""

from decimal import Decimal

from busybee.extract.notebook import add_entries
from busybee.extract.prompts import (
    RECORD_INSTRUCTIONS,
    RecordDraft,
    WindowOutput,
    build_user_prompt,
)
from busybee.schema.documents import Chunk
from busybee.schema.facts import EntryKind, FactCategory, FactScope

TABLE = Chunk(
    chunk_id="D1:p1:c0",
    doc_id="D1",
    page_no=1,
    index_in_page=0,
    text=(
        "Consolidated balance sheet (Rs crore)\n[TABLE: FY2024-25 | FY2023-24]\n"
        "Total borrowings | FY2024-25: 412.6 | FY2023-24: 380.1\n[/TABLE]"
    ),
)
OTHER = Chunk(chunk_id="D1:p2:c0", doc_id="D1", page_no=2, index_in_page=0, text="Unrelated prose.")


def test_prompt_asks_for_records_only_when_a_table_is_in_the_window() -> None:
    assert RECORD_INSTRUCTIONS in build_user_prompt("", "[D1:p1:c0]\n[TABLE: a | b]\nrow")
    assert RECORD_INSTRUCTIONS not in build_user_prompt("", "[D1:p2:c0]\nplain prose")


def test_window_output_parses_loose_record_values() -> None:
    output = WindowOutput.model_validate(
        {
            "entries": [],
            "records": [
                {
                    "metric": "Total borrowings",
                    "value": "1,845.32",
                    "previous_value": "(12.5)",
                    "scope": "Consolidated",
                    "chunk_ids": ["D1:p1:c0"],
                },
                {"metric": "Broken", "value": "n/a", "scope": "group"},
            ],
        }
    )
    first, second = output.records
    assert first.value == Decimal("1845.32") and first.previous_value == Decimal("-12.5")
    assert first.scope is FactScope.consolidated
    assert second.value is None and second.scope is None


def test_records_become_templated_number_entries_with_guessed_category() -> None:
    draft = RecordDraft(
        metric="Total borrowings",
        value=Decimal("412.6"),
        unit="crore",
        period="FY2024-25",
        scope=FactScope.consolidated,
        previous_value=Decimal("380.1"),
        previous_period="FY2023-24",
        chunk_ids=["D1:p1:c0", "D1:p9:c9"],
        importance=4,
    )
    unusable = RecordDraft(metric="Broken", chunk_ids=["D1:p1:c0"])
    kept, dropped = add_entries(
        [draft, unusable],
        doc_id="D1",
        window_no=1,
        chunks_by_id={TABLE.chunk_id: TABLE},
        window_chunks=[TABLE],
    )
    assert dropped == [] and len(kept) == 1
    entry = kept[0]
    assert entry.statement == (
        "Consolidated total borrowings was INR 412.6 crore in FY2024-25 "
        "(FY2023-24: INR 380.1 crore)."
    )
    assert entry.record is not None and entry.record.metric == "Total borrowings"
    assert (entry.kind, entry.category, entry.importance) == (
        EntryKind.number,
        FactCategory.debt_leverage,
        4,
    )
    assert [c.chunk_id for c in entry.citations] == ["D1:p1:c0"]


def test_record_without_chunk_id_is_rescued_from_its_numbers() -> None:
    draft = RecordDraft(
        metric="Total borrowings", value=Decimal("412.6"), unit="crore", period="FY2024-25"
    )
    kept, dropped = add_entries(
        [draft], doc_id="D1", window_no=1, chunks_by_id={}, window_chunks=[OTHER, TABLE]
    )
    assert dropped == [] and kept[0].citation_inferred
    assert [c.chunk_id for c in kept[0].citations] == ["D1:p1:c0"]
    absent = RecordDraft(metric="Total borrowings", value=Decimal("777"), unit="crore")
    _, dropped = add_entries(
        [absent], doc_id="D1", window_no=1, chunks_by_id={}, window_chunks=[OTHER, TABLE]
    )
    assert len(dropped) == 1
