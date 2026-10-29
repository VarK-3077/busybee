"""Indoco v7 regression: consolidated components missed by extraction are recovered by search.

The chunks are copied from the v7 corpus (consolidated balance sheet and cash-flow pages plus the
standalone pages that outranked them). The notebook lacks lease liabilities, cash, bank balances
and income tax paid; net debt and CFADS were bound partly, so only a search of partly bound
derived slots on the reporting basis recovers them. The mock provider answers the model calls.
"""

import json
import re
from pathlib import Path

import numpy as np
from policy_helpers import BANKS_DIR, write_facts

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingResult
from busybee.policy.components import normalise_component
from busybee.policy.slot_search import fill_unbound_slots, page_bases, search_targets
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, FactScope, NumericValue, VerifiedFact

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_v7_chunks.json"
ROW_MARKERS = {
    "non-current lease liabilities": "Note No.: 22b",
    "current lease liabilities": "Note No.: 26b",
    "cash and cash equivalents": "(iii) Cash and Cash Equivalents",
    "bank balances other than cash and cash equivalents": "Bank Balances other than (iii)",
    "income tax paid": "Income Tax Paid (Net of Refund)",
}


def _chunks() -> list[Chunk]:
    return [Chunk.model_validate(item) for item in json.loads(FIXTURE.read_text())]


def _fact(number: int, statement: str, chunk_id: str, scope: FactScope, value: str) -> VerifiedFact:
    return VerifiedFact(
        fact_id=f"F{number:03d}",
        statement=statement,
        scope=scope,
        citations=[Citation(chunk_id=chunk_id, doc_id="D1", page_no=271, quote=statement)],
        numbers=[NumericValue(label="x", value=value, unit="INR lakh", period="March 31, 2026")],
    )


def _notebook() -> list[VerifiedFact]:
    consolidated = FactScope.consolidated
    rows = [
        ("Consolidated total borrowings was INR 103,584.47 lakh as at March 31, 2026", "103584.47"),
        ("Consolidated EBITDA was INR 14,181.82 lakh in the year ended March 31, 2026", "14181.82"),
        ("Consolidated total equity was INR 93,211.18 lakh as at March 31, 2026", "93211.18"),
        (
            "Consolidated total current assets were INR 119,335.33 lakh as at March 31, 2026",
            "119335.33",
        ),
        (
            "Consolidated total current liabilities were INR 105,254.26 lakh as at March 31, 2026",
            "105254.26",
        ),
    ]
    facts = [
        _fact(i, text, "D1:p271:c1", consolidated, value) for i, (text, value) in enumerate(rows, 1)
    ]
    standalone = (
        "Standalone cash and cash equivalents at the end of the year was INR 1,293.72 lakh as at "
        "March 31, 2026"
    )
    return [*facts, _fact(6, standalone, "D1:p190:c0", FactScope.standalone, "1293.72")]


def _row(passage: str, marker: str) -> str | None:
    for line in passage.splitlines():
        if marker in line:
            return line
    return None


def _responder(messages: list[Message], task: str) -> str:
    content = messages[-1].content
    if task == "policy.slot_extract":
        item = re.search(r"^Component: (.+)$", content, re.M).group(1)
        marker = ROW_MARKERS.get(item)
        line = _row(content.split("]:\n", 1)[-1], marker) if marker else None
        if line is None:
            return json.dumps({"found": False})
        figure = re.findall(r"\(?[\d,]+\.\d+\)?", line)[0]
        return json.dumps(
            {
                "found": True,
                "statement": f"{item} was INR {figure} lakh in FY2026",
                "value": figure,
                "unit": "INR lakh",
                "period": "FY2026",
                "quote": line,
            }
        )
    if task == "verify_entailment":
        return json.dumps({"verdict": "supported", "quote": "", "note": ""})
    return json.dumps({"bindings": []})


async def _workspace(tmp_path: Path, chunks: list[Chunk], facts: list[VerifiedFact]) -> None:
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add(chunks, await embedder.embed([c.text for c in chunks]))
    store.save(tmp_path / "index")
    write_facts(tmp_path, facts)


def _fss():
    return [s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id.startswith("fin")]


def test_page_bases_read_the_statement_headings() -> None:
    bases = page_bases(_chunks())
    assert bases[("D1", 271)] == "consolidated" and bases[("D1", 274)] == "consolidated"
    assert bases[("D1", 187)] == "standalone" and bases[("D1", 190)] == "standalone"


def test_partly_bound_derived_slots_are_targeted_with_the_basis_word() -> None:
    targets = search_targets(_fss(), BindingResult(), _notebook())
    phrases = {t.phrase for t in targets}
    assert {
        "non-current lease liabilities",
        "current lease liabilities",
        "cash and cash equivalents",
        "bank balances other than cash and cash equivalents",
        "income tax paid",
    } <= phrases
    assert {t.basis for t in targets} == {"consolidated"}
    assert {normalise_component(t.slot.slot) for t in targets} >= {"net debt", "cfads"}


async def test_consolidated_components_are_recovered_from_the_vector_store(tmp_path) -> None:
    facts = _notebook()
    await _workspace(tmp_path, _chunks(), facts)
    result = await fill_unbound_slots(
        tmp_path, MockProvider(_responder), _fss(), facts, BindingResult()
    )
    figures = {str(fact.numbers[0].value) for fact in result.added}
    assert all(fact.statement.startswith("Consolidated") for fact in result.added)
    assert {"4233.88", "1155.73", "2592.78", "706.12"} <= figures
    tax = [f for f in result.added if "income tax paid" in f.statement.lower()]
    assert tax and "616.66" in tax[0].statement
    assert all(
        fact.citations[0].chunk_id in {"D1:p271:c1", "D1:p271:c2", "D1:p273:c1"}
        for fact in result.added
    )
    log = json.loads((tmp_path / "slot_search.json").read_text())
    for search in log["searches"]:
        assert search["queries"] and search["queries"][0].startswith("consolidated")
        assert all(
            not hit["chunk_id"].startswith(("D1:p187", "D1:p190", "D1:p189"))
            for hit in search["hits"][:1]
        )
