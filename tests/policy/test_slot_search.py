"""On-demand slot search: unbound slots are fetched from the index, verified, appended, bound."""

import json
import re
from decimal import Decimal

import numpy as np
from policy_helpers import write_facts

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.policy.bind_inputs import bind_inputs
from busybee.policy.slot_search import fill_unbound_slots, rebind_slots
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, NumericValue, VerifiedFact
from busybee.schema.policy import InputSlot, ScoreSpec

INTEREST = "Interest paid in FY2025 was INR 123.45 crore"
PRINCIPAL = "Repayment of long term borrowings in FY2025 was INR 80.00 crore"
DISTRACTORS = [
    "The registered office of the company is located in Mumbai",
    "Employee benefit expense rose with headcount across plants",
    "Statutory auditors were reappointed for a term of five years",
]
SPEC = ScoreSpec(
    score_id="dscr_score",
    name="DSCR",
    inputs=[
        InputSlot(
            slot="debt_service",
            description="Interest paid plus scheduled principal repayments in the year",
            unit="INR crore x 100",
            scale=100,
            definition="Interest paid plus scheduled principal repayments in the latest year.",
            derive_from=["interest paid", "scheduled principal repayments"],
        )
    ],
)


def _chunk(number: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"D1:p{number}:c0", doc_id="D1", page_no=number, index_in_page=0, text=text
    )


async def _index(workspace, texts: list[str]) -> None:
    embedder = HashingEmbedder()
    chunks = [_chunk(number, text) for number, text in enumerate(texts, start=1)]
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add(chunks, await embedder.embed([c.text for c in chunks]))
    store.save(workspace / "index")


def _revenue_fact() -> VerifiedFact:
    return VerifiedFact(
        fact_id="F001",
        statement="Revenue from operations was INR 5000.00 crore in FY2025",
        citations=[Citation(chunk_id="D1:p9:c0", doc_id="D1", page_no=9, quote="Revenue")],
        numbers=[NumericValue(label="Revenue", value=Decimal("5000"), unit="INR crore")],
    )


def _responder(messages: list[Message], task: str) -> str:
    content = messages[-1].content
    if task == "policy.slot_extract":
        phrase = re.search(r"^Component: (.+)$", content, re.M).group(1).lower()
        for line in content.split("]:\n", 1)[-1].splitlines():
            if phrase in line.lower():
                number = re.search(r"[\d.]+(?= crore)", line).group(0)
                return json.dumps(
                    {"found": True, "statement": line, "value": number, "quote": line}
                )
        return json.dumps({"found": False})
    if task == "verify_entailment":
        statement = content.split("Statement:\n", 1)[1].split("\n\nSource passage:\n")[0]
        passage = content.split("Source passage:\n", 1)[1]
        ok = statement in passage
        return json.dumps(
            {
                "verdict": "supported" if ok else "unsupported",
                "quote": statement if ok else "",
                "note": "",
            }
        )
    return json.dumps({"bindings": []})


async def _unbound(workspace, texts: list[str], budget: int = 24):
    await _index(workspace, texts)
    facts = [_revenue_fact()]
    write_facts(workspace, facts)
    provider = MockProvider(_responder)
    binding = await bind_inputs(provider, [SPEC], facts)
    assert ("dscr_score", "debt_service") in binding.unbound
    result = await fill_unbound_slots(workspace, provider, [SPEC], facts, binding, budget=budget)
    return provider, facts, binding, result


async def test_unbound_derived_slot_gets_both_components_and_binds(tmp_path) -> None:
    provider, facts, binding, result = await _unbound(tmp_path, [INTEREST, PRINCIPAL, *DISTRACTORS])
    assert [f.fact_id for f in result.added] == ["F002", "F003"]
    saved = json.loads((tmp_path / "verified_facts.json").read_text())
    assert [f["added_by"] for f in saved[1:]] == ["slot_search", "slot_search"]
    assert saved[1]["citations"][0]["chunk_id"] == "D1:p1:c0"
    facts = [*facts, *result.added]
    merged = await rebind_slots(provider, [SPEC], facts, binding, result.slots, [])
    bound = {item.slot: item for item in merged.bound["dscr_score"]}
    assert bound["debt_service"].value_scaled == 20345
    assert ("dscr_score", "debt_service") not in merged.unbound
    log = json.loads((tmp_path / "slot_search.json").read_text())
    assert log["added_fact_ids"] == ["F002", "F003"]
    assert log["budget"]["extract_calls"] == result.calls <= 8
    first = log["searches"][0]
    assert first["component"] == "interest paid" and 1 <= len(first["queries"]) <= 5
    assert first["hits"][-1]["outcome"] == "found" and first["outcome"] == "verified"


async def test_slot_absent_from_the_corpus_stays_unbound_with_a_log(tmp_path) -> None:
    _, facts, binding, result = await _unbound(tmp_path, DISTRACTORS)
    assert result.added == [] and result.slots == set()
    assert json.loads((tmp_path / "verified_facts.json").read_text())[0]["fact_id"] == "F001"
    log = json.loads((tmp_path / "slot_search.json").read_text())
    assert [s["outcome"] for s in log["searches"]] == ["not_found"] * 3
    assert all(h["outcome"] == "not_found" for s in log["searches"] for h in s["hits"])
    assert all(len(s["hits"]) <= 6 for s in log["searches"])
    assert ("dscr_score", "debt_service") in binding.unbound


async def test_budget_limits_extract_calls(tmp_path) -> None:
    _, _, _, result = await _unbound(tmp_path, DISTRACTORS, budget=2)
    assert result.calls == 2
    log = json.loads((tmp_path / "slot_search.json").read_text())
    assert log["budget"] == {"per_component": 6, "per_run": 2, "extract_calls": 2}
    assert log["searches"][1]["outcome"] == "budget_exhausted"


async def test_zero_budget_disables_the_search(tmp_path) -> None:
    _, _, _, result = await _unbound(tmp_path, [INTEREST, PRINCIPAL], budget=0)
    assert result.calls == 0 and result.added == []
