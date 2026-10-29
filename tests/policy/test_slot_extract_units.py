"""Slot extract units: the table or page header sets the unit, never the model's word alone.

Indoco v8 recorded consolidated current lease liabilities as "1,155.73 INR crore" from a note
table whose unit line ("All amounts in INR lakhs") sits in the chunk above the table. The page
was also a standalone note headed "Notes (Standalone)", which must not feed consolidated slots.
"""

import json
import re

import numpy as np
from policy_helpers import BANKS_DIR, write_facts
from test_rebind_after_search import _facts

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingResult
from busybee.policy.slot_search import (
    _last_unit,
    chunk_unit,
    fill_unbound_slots,
    page_bases,
    with_unit,
)
from busybee.schema.documents import Chunk

TABLE = (
    "Note 26b : Current Financial - Lease Liabilities\nParticulars\n"
    "[TABLE: March 31, 2026 | March 31, 2025]\n"
    "Total, Current Financial Lease Liabilities | March 31, 2026: 1,155.73 | "
    "March 31, 2025: 617.49\n[/TABLE]"
)


def _page(page: int, heading: str) -> list[Chunk]:
    head = (
        f"{heading}\non financial statements for the year ended March 31, 2026\n"
        "(All amounts in INR lakhs, unless otherwise stated)\n"
        "Note 26a : Current Financial Liabilities - Borrowings"
    )
    return [
        Chunk(chunk_id=f"D1:p{page}:c0", doc_id="D1", page_no=page, index_in_page=0, text=head),
        Chunk(chunk_id=f"D1:p{page}:c1", doc_id="D1", page_no=page, index_in_page=1, text=TABLE),
    ]


def test_header_variants_give_the_unit() -> None:
    cases = {
        "(All amounts in INR lakhs, unless otherwise stated)": "lakh",
        "(₹ in lakhs)": "lakh",
        "(` in lakhs)": "lakh",
        "(Rs. lakh)": "lakh",
        "Rs. in Crores": "crore",
        "Rs. Mn": "million",
        "(INR million)": "million",
        "(₹ '000)": "thousand",
        "(Amount in ₹ thousand)": "thousand",
        "Revenue was INR 1,234 lakh": "",
    }
    assert {text: _last_unit(text) for text in cases} == cases


def test_unit_comes_from_an_earlier_chunk_of_the_same_page() -> None:
    first, table = _page(224, "Notes (Consolidated)")
    assert chunk_unit(table, [first, table], "Total, Current Financial Lease") == "lakh"
    prefixed = table.model_copy(update={"prefix": "[TABLE: Note | (Rs. in crore)]"})
    assert chunk_unit(prefixed, [first, prefixed]) == "crore"


def test_statement_figure_is_rewritten_with_the_header_unit() -> None:
    wrong = "Consolidated current lease liabilities were 1,155.73 INR crore as at March 31, 2026."
    assert with_unit(wrong, "1,155.73", "lakh") == (
        "Consolidated current lease liabilities were INR 1,155.73 lakh as at March 31, 2026."
    )
    outflow = "Repayment of term loans for the year ended March 31, 2026 was (7,403.04)."
    assert with_unit(outflow, "(7,403.04)", "lakh").endswith("was an outflow of INR 7,403.04 lakh.")


def test_notes_headed_standalone_are_a_standalone_page() -> None:
    chunks = [*_page(224, "Notes (Standalone)"), *_page(300, "Notes (Consolidated)")]
    bases = page_bases(chunks)
    assert bases[("D1", 224)] == "standalone" and bases[("D1", 300)] == "consolidated"


def _responder(messages: list[Message], task: str) -> str:
    content = messages[-1].content
    if task == "policy.slot_extract":
        component = re.search(r"^Component: (.+)$", content, re.M).group(1)
        if component != "current lease liabilities" or "1,155.73" not in content:
            return json.dumps({"found": False})
        return json.dumps(
            {
                "found": True,
                "statement": "Current lease liabilities were 1,155.73 INR crore as at "
                "March 31, 2026",
                "value": "1,155.73",
                "unit": "INR crore",
                "period": "March 31, 2026",
                "quote": "Total, Current Financial Lease Liabilities | March 31, 2026: 1,155.73",
            }
        )
    if task == "verify_entailment":
        return json.dumps({"verdict": "supported", "quote": "", "note": ""})
    return json.dumps({"bindings": []})


async def test_search_records_the_header_unit_and_skips_the_standalone_page(tmp_path) -> None:
    chunks = [*_page(224, "Notes (Standalone)"), *_page(300, "Notes (Consolidated)")]
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add(chunks, await embedder.embed([c.text for c in chunks]))
    store.save(tmp_path / "index")
    facts = _facts(skip={"F189", "F190", "F191", "F192", "F195", "F196"})
    write_facts(tmp_path, facts)
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id.startswith("fin"))
    spec = spec.model_copy(update={"inputs": [i for i in spec.inputs if i.slot == "net_debt"]})
    result = await fill_unbound_slots(
        tmp_path, MockProvider(_responder), [spec], facts, BindingResult()
    )
    lease = [f for f in result.added if "lease" in f.statement.lower()]
    assert len(lease) == 1
    fact = lease[0]
    assert "INR 1,155.73 lakh" in fact.statement and "crore" not in fact.statement
    assert fact.numbers[0].unit == "INR lakh"
    assert fact.citations[0].page_no == 300
    log = json.loads((tmp_path / "slot_search.json").read_text())
    outcomes = {h["chunk_id"]: h["outcome"] for s in log["searches"] for h in s["hits"]}
    assert all(v == "other_basis" for k, v in outcomes.items() if k.startswith("D1:p224"))
