"""A statement row printed as a dash or Nil in the target-year column is a stated zero.

Companies with no current investments print "Current investments | March 31, 2026: - | ...".
The slot search must read that as 0 (so net debt has no missing component), but only when the
row is in the table with the dash under the target year; an absent row stays missing and a dash
in the prior-year column alone says nothing about the current year.
"""

import json
from decimal import Decimal

import numpy as np
import pytest
from policy_helpers import write_facts
from test_rebind_after_search import _facts, _spec, _v8_binding

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import MockProvider
from busybee.policy.bind_inputs import BindingResult, line_item_stated
from busybee.policy.complete_derived import complete_derived_slots
from busybee.policy.nil_rows import is_nil_entry, nil_fact, nil_row_entry
from busybee.policy.slot_search import fill_unbound_slots
from busybee.schema.documents import Chunk
from busybee.schema.facts import FactCategory, FactScope

HEADER = (
    "Consolidated balance sheet as at March 31, 2026\n"
    "(All amounts in INR lakhs, unless otherwise stated)\n"
)


def _table(row: str) -> Chunk:
    text = (
        f"{HEADER}[TABLE: March 31, 2026 | March 31, 2025]\n"
        "Trade receivables | March 31, 2026: 1,200.50 | March 31, 2025: 900.00\n"
        f"{row}\n[/TABLE]"
    )
    return Chunk(chunk_id="D1:p9:c0", doc_id="D1", page_no=9, index_in_page=0, text=text)


def _entry(
    chunk: Chunk,
    phrase: str = "current investments",
    basis: str = "consolidated",
    unit: str = "lakh",
):
    return nil_row_entry(
        chunk, phrase, 2026, unit, basis, "SLOT:E001", FactCategory.liquidity, 4, "slot_search"
    )


@pytest.mark.parametrize("cell", ["-", "–", "—", "−", "- ", "Nil", "NIL", "nil"])
def test_dash_and_nil_cells_in_the_target_column_are_zero(cell: str) -> None:
    chunk = _table(f"Current investments | March 31, 2026: {cell} | March 31, 2025: 55.00")
    entry = _entry(chunk)
    assert entry is not None and is_nil_entry(entry)
    assert entry.entry_id == "SLOT:N001"
    assert entry.statement == (
        "Consolidated current investments were nil (INR 0 lakh) as at March 31, 2026"
    )
    assert entry.citations[0].chunk_id == "D1:p9:c0"
    assert entry.citations[0].quote in chunk.text
    fact = nil_fact(entry)
    assert [n.value for n in fact.numbers] == [Decimal(0)]
    assert fact.numbers[0].unit == "INR lakh"


def test_other_wording_of_the_row_and_header_formats_match() -> None:
    chunk = Chunk(
        chunk_id="D1:p9:c0",
        doc_id="D1",
        page_no=9,
        index_in_page=0,
        text=(
            "[TABLE: FY 2025-26 | FY 2024-25]\n"
            "(a) Current Investments | FY 2025-26: Nil | FY 2024-25: 4"
        ),
    )
    entry = _entry(chunk, basis="", unit="")
    assert entry is not None
    assert entry.statement == "Current Investments were nil (INR 0 crore) in FY2026"


def test_row_absent_from_the_page_stays_missing() -> None:
    assert _entry(_table("Inventories | March 31, 2026: - | March 31, 2025: 3.00")) is None
    assert _entry(_table("Non-current investments | March 31, 2026: - | March 31, 2025: 3")) is None


def test_dash_in_the_prior_year_column_only_does_not_count() -> None:
    assert _entry(_table("Current investments | March 31, 2026: 77.00 | March 31, 2025: -")) is None
    assert _entry(_table("Current investments | March 31, 2025: - | March 31, 2026: 77.00")) is None


def test_a_row_without_a_named_year_column_is_not_read() -> None:
    chunk = Chunk(
        chunk_id="D1:p9:c0",
        doc_id="D1",
        page_no=9,
        index_in_page=0,
        text="Current investments | - | -",
    )
    assert _entry(chunk) is None


async def test_search_adds_a_nil_fact_and_net_debt_loses_the_missing_component(tmp_path) -> None:
    chunk = _table("Current investments | March 31, 2026: - | March 31, 2025: 55.00")
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add([chunk], await embedder.embed([chunk.text]))
    store.save(tmp_path / "index")
    facts = _facts()
    write_facts(tmp_path, facts)
    provider = MockProvider(lambda messages, task: json.dumps({"found": False}))
    result = await fill_unbound_slots(
        tmp_path, provider, _spec(), facts, BindingResult(basis=FactScope.consolidated)
    )
    nil = [f for f in result.added if "current investments" in f.statement.lower()]
    assert len(nil) == 1
    assert nil[0].verification.method == "nil_row_match"
    assert nil[0].citations[0].chunk_id == "D1:p9:c0"
    log = json.loads((tmp_path / "slot_search.json").read_text())
    assert any(s["component"] == "current investments" and s["fact_id"] for s in log["searches"])
    assert line_item_stated(
        "current investments", "liquid investments", [*facts, *nil], FactScope.consolidated
    )
    bound = {
        i.slot: i
        for i in complete_derived_slots(_spec(), _v8_binding(), [*facts, *nil]).bound[
            "financial_strength_score"
        ]
    }
    assert bound["net_debt"].missing == []
    assert "liquid investments" not in bound["net_debt"].caution


async def test_search_without_a_nil_row_leaves_the_component_missing(tmp_path) -> None:
    chunk = _table("Inventories | March 31, 2026: - | March 31, 2025: 55.00")
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add([chunk], await embedder.embed([chunk.text]))
    store.save(tmp_path / "index")
    facts = _facts()
    write_facts(tmp_path, facts)
    provider = MockProvider(lambda messages, task: json.dumps({"found": False}))
    result = await fill_unbound_slots(
        tmp_path, provider, _spec(), facts, BindingResult(basis=FactScope.consolidated)
    )
    assert not [f for f in result.added if "investments" in f.statement.lower()]
    bound = complete_derived_slots(_spec(), _v8_binding(), facts).bound["financial_strength_score"]
    assert {i.slot: i for i in bound}["net_debt"].missing == ["liquid investments"]
