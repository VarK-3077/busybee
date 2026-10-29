"""Full verify_entries flow: supported, resupported, unsupported and dropped-irrelevant."""

import json

from busybee.llm import Message, MockProvider
from busybee.schema.facts import VerificationStatus
from busybee.verify.verify_entries import VerifyContext, verify_entries

from .helpers import judge_provider, make_chunk, make_entry, make_store

CHUNKS = [
    make_chunk("D1:p1:c0", "Revenue for FY24 was Rs 1,200 crore, up 12% year on year."),
    make_chunk("D1:p2:c0", "Total borrowings were Rs 300 crore at 31 March 2024."),
    make_chunk("D1:p3:c0", "The board met four times."),
]


async def build_ctx(provider) -> VerifyContext:  # noqa: ANN001
    store, embedder = await make_store(CHUNKS)
    return VerifyContext(
        provider=provider,
        chunks_by_id={c.chunk_id: c for c in CHUNKS},
        store=store,
        embedder=embedder,
        notebook_context="ctx",
    )


def entries():  # noqa: ANN201
    return [
        make_entry("E1", "Revenue for FY24 was Rs 1,200 crore", "D1:p1:c0"),
        make_entry("E2", "Total borrowings were Rs 300 crore", "D1:p3:c0"),
        make_entry("E3", "Promoter holding is 75% of equity", "D1:p3:c0"),
        make_entry("E4", "The board has a cheerful tone", "D1:p3:c0"),
        make_entry("E5", "Revenue grew 12% year on year", "D1:p2:c0"),
    ]


async def test_flow_covers_all_outcomes() -> None:
    provider = judge_provider(
        is_relevant=lambda i: i != "E4",
        supports=lambda s, p: "300 crore" in p or "12%" in p,
    )
    facts, dropped = await verify_entries(entries(), await build_ctx(provider))

    by_source = {f.source_entry_id: f for f in facts}
    assert [f.source_entry_id for f in facts] == ["E1", "E2", "E5"]
    assert by_source["E1"].verification.status is VerificationStatus.supported
    assert by_source["E1"].verification.method == "exact_match"
    assert by_source["E1"].citations[0].quote in CHUNKS[0].text
    assert by_source["E2"].verification.status is VerificationStatus.resupported
    assert by_source["E2"].citations[0].chunk_id == "D1:p2:c0"
    assert by_source["E5"].verification.status is VerificationStatus.resupported
    assert by_source["E5"].citations[0].chunk_id == "D1:p1:c0"

    assert [d.entry.entry_id for d in dropped] == ["E3", "E4"]
    assert dropped[0].stage == "verify.citation"
    assert "75" in dropped[0].reason
    assert dropped[1].stage == "verify.relevance"
    assert dropped[1].reason.startswith("not relevant")


async def test_llm_entailment_path_and_numbers() -> None:
    provider = judge_provider(supports=lambda s, p: True)
    entry = make_entry("E1", "FY24 revenue was Rs 1,200 crore and grew 12%", "D1:p1:c0")
    facts, dropped = await verify_entries([entry], await build_ctx(provider))
    assert dropped == []
    fact = facts[0]
    assert fact.verification.method == "llm_entailment"
    assert fact.fact_id == ""
    assert {n.unit for n in fact.numbers} >= {"%", "INR crore"}
    assert all(n.period == "FY24" for n in fact.numbers)


async def test_added_by_is_carried_and_relevance_can_be_skipped() -> None:
    provider = judge_provider(is_relevant=lambda i: False)
    entry = make_entry("E1", "Revenue for FY24 was Rs 1,200 crore", "D1:p1:c0")
    entry.added_by = "adversary"
    facts, _ = await verify_entries([entry], await build_ctx(provider), check_relevance=False)
    assert facts[0].added_by == "adversary"
    assert provider.calls == []


async def test_results_are_in_input_order() -> None:
    provider = judge_provider(supports=lambda s, p: True)
    es = [make_entry(f"E{i}", "Revenue for FY24 was Rs 1,200 crore", "D1:p1:c0") for i in range(6)]
    facts, _ = await verify_entries(es, await build_ctx(provider))
    assert [f.source_entry_id for f in facts] == [f"E{i}" for i in range(6)]


async def test_importance_is_carried_from_the_entry() -> None:
    entry = make_entry("E1", "Revenue for FY24 was Rs 1,200 crore", "D1:p1:c0")
    entry = entry.model_copy(update={"importance": 5})
    provider = judge_provider(is_relevant=lambda i: True, supports=lambda s, p: True)
    facts, _ = await verify_entries([entry], await build_ctx(provider))
    assert [f.importance for f in facts] == [5]


SPLIT = [
    make_chunk(
        "D1:p9:c0", "Consolidated results. FY25 Revenue from operations was Rs 931.2 crore."
    ),
    make_chunk("D1:p9:c1", "FY25 Net profit was Rs 85.4 crore, up from the prior year."),
    make_chunk("D1:p9:c2", "Unrelated board matters."),
]


async def split_ctx(provider) -> VerifyContext:  # noqa: ANN001
    return VerifyContext(
        provider=provider, chunks_by_id={c.chunk_id: c for c in SPLIT}, store=None, embedder=None
    )


async def test_numbers_split_across_adjacent_chunks_cite_both() -> None:
    entry = make_entry(
        "E1", "Revenue was Rs 931.2 crore and net profit Rs 85.4 crore in FY25", "D1:p9:c0"
    )
    provider = judge_provider(supports=lambda s, p: "931.2" in p and "85.4" in p)
    facts, dropped = await verify_entries([entry], await split_ctx(provider), check_relevance=False)
    assert not dropped
    assert [c.chunk_id for c in facts[0].citations] == ["D1:p9:c0", "D1:p9:c1"]
    assert facts[0].verification.method == "llm_entailment+adjacent_chunks"


async def test_adjacent_fallback_dropped_when_judge_rejects_concatenation() -> None:
    entry = make_entry(
        "E1", "Revenue was Rs 931.2 crore and net profit Rs 85.4 crore in FY25", "D1:p9:c0"
    )
    provider = judge_provider(supports=lambda s, p: False)
    facts, dropped = await verify_entries([entry], await split_ctx(provider), check_relevance=False)
    assert not facts and len(dropped) == 1


async def test_adjacent_fallback_not_tried_when_no_number_is_in_cited_chunk() -> None:
    entry = make_entry("E1", "Net profit was Rs 85.4 crore in FY25", "D1:p9:c2")
    provider = judge_provider(supports=lambda s, p: True)
    facts, dropped = await verify_entries([entry], await split_ctx(provider), check_relevance=False)
    assert not facts and len(dropped) == 1


def _quoting(quote: str) -> MockProvider:
    def respond(messages: list[Message], task: str) -> str:
        return json.dumps({"verdict": "supported", "quote": quote, "note": "ok"})

    return MockProvider(respond)


async def _adjacent_quotes(quote: str) -> list[tuple[str, str]]:
    entry = make_entry(
        "E1", "Revenue was Rs 931.2 crore and net profit Rs 85.4 crore in FY25", "D1:p9:c0"
    )
    ctx = await split_ctx(_quoting(quote))
    facts, _ = await verify_entries([entry], ctx, check_relevance=False)
    assert facts[0].verification.method == "llm_entailment+adjacent_chunks"
    return [(c.chunk_id, c.quote) for c in facts[0].citations]


async def test_adjacent_citation_quote_from_one_chunk_is_not_blank_on_the_others() -> None:
    quotes = await _adjacent_quotes("FY25 Net profit was Rs 85.4 crore")
    assert [chunk_id for chunk_id, _ in quotes] == ["D1:p9:c0", "D1:p9:c1"]
    for chunk_id, quote in quotes:
        assert quote.strip() and quote in next(c.text for c in SPLIT if c.chunk_id == chunk_id)
    assert quotes[0][1].endswith("FY25 Revenue from operations was Rs 931.2 crore.")


async def test_adjacent_citation_quote_spanning_two_chunks_is_cut_per_chunk() -> None:
    spanning = "FY25 Revenue from operations was Rs 931.2 crore.\nFY25 Net profit was Rs 85.4 crore"
    quotes = await _adjacent_quotes(spanning)
    texts = {c.chunk_id: c.text for c in SPLIT}
    assert all(quote and quote in texts[chunk_id] for chunk_id, quote in quotes)
    assert quotes[1][1] == "FY25 Net profit was Rs 85.4 crore"
