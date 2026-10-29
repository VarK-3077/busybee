"""Tests for the condensed notebook text and the over-budget merge path."""

import json

from busybee.extract.condense import (
    condense_entries,
    merge_groups,
    should_condense,
)
from busybee.extract.condensed import condense_entry, condense_notebook
from busybee.llm import MockProvider
from busybee.schema.facts import Citation, EntryKind, FactCategory, NotebookEntry


def entry(
    entry_id: str,
    statement: str,
    chunk_id: str,
    *,
    importance: int = 3,
) -> NotebookEntry:
    doc_id = chunk_id.split(":")[0]
    return NotebookEntry(
        entry_id=entry_id,
        statement=statement,
        citations=[Citation(chunk_id=chunk_id, doc_id=doc_id, page_no=1)],
        category=FactCategory.revenue,
        kind=EntryKind.number,
        importance=importance,
        doc_id=doc_id,
    )


def test_condensed_line_has_the_documented_shape() -> None:
    item = entry("D1:E012", "Revenue was INR 931.2 crore in FY25.", "D1:p12:c3", importance=4)

    line = condense_entry(item)

    assert line == (
        "D1:E012 | revenue | imp 4 | Revenue was INR 931.2 crore in FY25. | cites D1:p12:c3"
    )


def test_condensed_statement_is_one_line_and_at_most_160_chars() -> None:
    statement = "Revenue grew sharply. " + "detail " * 40
    item = entry("D1:E001", statement, "D1:p1:c0")

    line = condense_entry(item)
    rendered_statement = line.split(" | ")[3]

    assert "\n" not in line
    assert len(rendered_statement) <= 160


def test_condense_notebook_keeps_entry_order() -> None:
    first = entry("D1:E001", "Revenue was 100.", "D1:p1:c0")
    second = entry("D1:E002", "Revenue was 120.", "D1:p1:c1")

    text = condense_notebook([first, second])

    assert text.splitlines()[0].startswith("D1:E001 |")
    assert text.splitlines()[1].startswith("D1:E002 |")


def test_should_condense_compares_against_the_budget() -> None:
    items = [entry("D1:E001", "Revenue was 100 crore in FY25.", "D1:p1:c0")]

    assert should_condense(items, 0)
    assert not should_condense(items, 10_000)


async def test_condense_entries_merges_groups_and_unions_citations() -> None:
    first = entry("D1:E001", "Revenue was 100 crore.", "D1:p1:c0", importance=3)
    second = entry("D1:E002", "Revenue was 100 crore.", "D2:p2:c1", importance=5)
    provider = MockProvider({"condense": [json.dumps({"groups": [["D1:E001", "D1:E002"]]})]})

    merged = await condense_entries([first, second], provider, budget_tokens=0)

    assert len(merged) == 1
    assert merged[0].entry_id == "D1:E001"
    assert merged[0].importance == 5
    assert [citation.chunk_id for citation in merged[0].citations] == [
        "D1:p1:c0",
        "D2:p2:c1",
    ]
    assert provider.calls[0].task == "condense"


async def test_condense_entries_skips_the_llm_when_under_budget() -> None:
    items = [entry("D1:E001", "Revenue was 100 crore.", "D1:p1:c0")]
    provider = MockProvider({"condense": [json.dumps({"groups": []})]})

    result = await condense_entries(items, provider, budget_tokens=10_000)

    assert result == items
    assert provider.calls == []


def test_merge_groups_ignores_unknown_and_overlapping_ids() -> None:
    first = entry("D1:E001", "Revenue was 100 crore.", "D1:p1:c0")
    second = entry("D1:E002", "Revenue was 100 crore.", "D1:p1:c1")
    third = entry("D1:E003", "Cash was 20 crore.", "D1:p1:c2")

    merged = merge_groups(
        [first, second, third],
        [["D1:E001", "D9:E999"], ["D1:E001", "D1:E002"], ["D1:E002", "D1:E003"]],
    )

    assert [item.entry_id for item in merged] == ["D1:E001", "D1:E003"]


async def test_condense_entries_keeps_the_notebook_when_the_reply_is_truncated(
    monkeypatch,
) -> None:
    import busybee.extract.condense as condense_module
    from busybee.llm import StructuredOutputError

    async def truncated(*args, **kwargs):
        raise StructuredOutputError("reply truncated", truncated=True)

    monkeypatch.setattr(condense_module, "complete_as", truncated)
    items = [
        entry("D1:E001", "Revenue was 100 crore.", "D1:p1:c0"),
        entry("D1:E002", "Revenue was 100 crore.", "D2:p2:c1"),
    ]

    result = await condense_entries(items, MockProvider({}), budget_tokens=0)

    assert result == items
