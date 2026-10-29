"""Slot search query construction, prompt content and a replay of the indoco-v3 failure."""

import json
from decimal import Decimal

import numpy as np
from policy_helpers import write_facts
from test_slot_search import _revenue_fact

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.policy.bind_inputs import bind_inputs
from busybee.policy.slot_search import (
    _SYSTEM,
    HITS_PER_COMPONENT,
    MAX_QUERIES,
    SEARCH_K,
    Target,
    build_queries,
    cash_flow_wordings,
    definition_clause,
    fill_unbound_slots,
)
from busybee.schema.documents import Chunk
from busybee.schema.policy import InputSlot, ScoreSpec

DEFINITION = (
    "Interest paid plus scheduled principal repayments of borrowings (repayment of long-term "
    "borrowings and lease principal) in the latest audited year (policy section 4)."
)
SLOT = InputSlot(
    slot="debt_service",
    description="Interest paid plus scheduled principal repayments in the year",
    unit="INR crore x 100",
    scale=100,
    definition=DEFINITION,
    derive_from=["interest_paid", "scheduled_principal_repayments"],
)
SPEC = ScoreSpec(score_id="financial_strength_score", name="FS", inputs=[SLOT])
ROW = (
    "Repayment of Long Term Borrowings | Year ended 31.03.2026: (6,817.31) | "
    "... Contd. from previous page Year ended 31.03.2025: (4,190.50)"
)
CASH_FLOW = (
    "Cash Flow Statement\nFor the year ended March 31, 2026\n"
    "(C) Cash Flow from Financing Activities\n"
    "[TABLE: Year ended 31.03.2026 | ... Contd. from previous page Year ended 31.03.2025 "
    "| (` in lakhs)]\n"
    "Payment of Lease Liability | Year ended 31.03.2026: (1,095.62) | Year ended 31.03.2025: "
    "(523.32)\n" + ROW + "\n[/TABLE]"
)
RECORDED_NOT_FOUND = ['{\n  "found": false\n}', '{"found": false}']


def _target(phrase: str) -> Target:
    return Target(SLOT, ("financial_strength_score",), phrase, True)


def test_principal_queries_use_cash_flow_line_wording_and_definition_clause() -> None:
    queries = build_queries(_target("scheduled principal repayments"), 2026)
    assert len(queries) <= MAX_QUERIES and len(queries) == len(set(queries))
    assert any(q.startswith("Repayment of long-term borrowings cash flow") for q in queries)
    assert any(
        q.startswith("scheduled principal repayments of borrowings (repayment") for q in queries
    )
    assert any("FY2026" in q for q in queries)


def test_interest_queries_name_the_finance_cost_line() -> None:
    queries = build_queries(_target("interest paid"), 2026)
    assert any(q.startswith("Interest paid cash flow") for q in queries)
    assert any(q.startswith("Finance costs paid") for q in queries)
    assert queries[-2].startswith("Interest paid plus scheduled principal repayments of")


def test_non_flow_phrase_gets_no_wordings_and_clause_is_verbatim() -> None:
    assert cash_flow_wordings("net worth") == []
    assert definition_clause(DEFINITION, "scheduled principal repayments").startswith(
        "scheduled principal repayments of borrowings (repayment of long-term"
    )
    assert definition_clause(DEFINITION, "dividends") == ""


def _chunk(number: int, text: str, prefix: str = "") -> Chunk:
    return Chunk(
        chunk_id=f"D1:p{number}:c0",
        doc_id="D1",
        page_no=number,
        index_in_page=0,
        text=text,
        prefix=prefix,
    )


async def _workspace(tmp_path, chunks: list[Chunk]):
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add(chunks, await embedder.embed([c.text for c in chunks]))
    store.save(tmp_path / "index")
    facts = [_revenue_fact()]
    write_facts(tmp_path, facts)
    return facts


def _replaying(found_reply: str | None):
    seen: list[str] = []

    def responder(messages: list[Message], task: str) -> str:
        content = messages[-1].content
        if task == "policy.slot_extract":
            seen.append(content)
            if found_reply and "Repayment of Long Term Borrowings" in content.split("Passage")[-1]:
                return found_reply
            return RECORDED_NOT_FOUND[len(seen) % 2]
        if task == "verify_entailment":
            quote = ROW.split(" | ...")[0]
            return json.dumps({"verdict": "supported", "quote": quote, "note": ""})
        return json.dumps({"bindings": []})

    return MockProvider(responder), seen


async def test_replayed_not_found_replies_are_logged_per_hit(tmp_path) -> None:
    facts = await _workspace(tmp_path, [_chunk(190, CASH_FLOW), _chunk(2, "Registered office")])
    provider, seen = _replaying(None)
    binding = await bind_inputs(provider, [SPEC], facts)
    result = await fill_unbound_slots(tmp_path, provider, [SPEC], facts, binding, budget=24)
    log = json.loads((tmp_path / "slot_search.json").read_text())
    assert result.added == []
    assert log["searches"][1]["hits"][0]["chunk_id"] == "D1:p190:c0"
    assert {h["outcome"] for s in log["searches"] for h in s["hits"]} == {"not_found"}
    assert len(seen) <= 2 * HITS_PER_COMPONENT and SEARCH_K == 12


async def test_prompt_shows_header_row_rules_and_bracket_figures_are_accepted(tmp_path) -> None:
    chunk = _chunk(190, CASH_FLOW, prefix="[TABLE: Year ended 31.03.2026 | (` in lakhs)]")
    facts = await _workspace(tmp_path, [chunk])
    reply = json.dumps(
        {
            "found": True,
            "statement": "Repayment of Long Term Borrowings was INR 6,817.31 lakh in FY2026",
            "value": "6,817.31",
            "unit": "INR lakh",
            "period": "FY2026",
            "quote": ROW.split(" | ...")[0],
        }
    )
    provider, seen = _replaying(reply)
    binding = await bind_inputs(provider, [SPEC], facts)
    result = await fill_unbound_slots(tmp_path, provider, [SPEC], facts, binding, budget=24)
    prompt = seen[-1]
    assert "Table header: [TABLE: Year ended 31.03.2026" in prompt
    assert "Usual statement wording of this row" in prompt
    assert "brackets" in _SYSTEM
    assert result.added and result.added[0].numbers[0].value == Decimal("6817.31")
