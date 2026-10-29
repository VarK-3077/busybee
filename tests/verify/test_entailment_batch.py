"""Several cited chunks are judged in one call, with per-chunk verbatim quotes and fallbacks."""

import json

from busybee.llm import MockProvider
from busybee.schema.documents import DocumentKind
from busybee.schema.facts import Citation, NotebookEntry
from busybee.verify.entailment import judge_entailment_batch
from busybee.verify.verify_entries import (
    REASON_SCORE_INPUT,
    VerifyContext,
    verify_entries,
)

from .helpers import judge_provider, make_chunk

A = make_chunk("D1:p1:c0", "Net debt stood at Rs 40 crore at 31 March 2024.")
B = make_chunk("D1:p2:c0", "Net debt was Rs 40 crore; the board met four times.")
PASSAGES = [(A.chunk_id, A.text), (B.chunk_id, B.text)]


def tasks(provider: MockProvider) -> list[str]:
    return [call["task"] for call in provider.calls]


async def test_two_chunks_one_call_with_per_chunk_verdicts() -> None:
    reply = {
        "r": [
            {"id": A.chunk_id, "v": "supported", "q": "Net debt stood at Rs 40"},
            {"id": B.chunk_id, "v": "unsupported"},
        ]
    }
    provider = MockProvider({"verify_entailment_batch": json.dumps(reply)})
    results = await judge_entailment_batch("Net debt is Rs 40 crore", PASSAGES, provider)
    assert tasks(provider) == ["verify_entailment_batch"]
    shown = provider.calls[0]["messages"][-1].content
    assert f"[{A.chunk_id}]" in shown and f"[{B.chunk_id}]" in shown
    assert [r.verdict.value for r in results] == ["supported", "unsupported"]
    assert results[0].quote == "Net debt stood at Rs 40"


async def test_quote_of_another_chunk_is_not_accepted() -> None:
    reply = {
        "r": [
            {"id": A.chunk_id, "v": "partial", "q": "the board met four times"},
            {"id": B.chunk_id, "v": "unsupported"},
        ]
    }
    provider = MockProvider({"verify_entailment_batch": json.dumps(reply)})
    results = await judge_entailment_batch("Net debt is Rs 40 crore", PASSAGES, provider)
    assert results[0].verdict.value == "partial"
    assert results[0].quote == A.text and results[0].note == "quote located by code"


async def test_unparseable_batch_reply_falls_back_to_one_call_per_chunk() -> None:
    def respond(messages, task):  # noqa: ANN001, ANN202
        if task == "verify_entailment_batch":
            return "not json"
        return json.dumps({"v": "unsupported"})

    provider = MockProvider(respond)
    results = await judge_entailment_batch("Net debt is Rs 40 crore", PASSAGES, provider)
    assert len(results) == 2
    assert tasks(provider).count("verify_entailment") == 2


async def test_chunk_missing_from_reply_is_judged_alone() -> None:
    def respond(messages, task):  # noqa: ANN001, ANN202
        if task == "verify_entailment_batch":
            item = {"id": A.chunk_id, "v": "unsupported"}
            return json.dumps({"r": [item]})
        return json.dumps({"v": "supported", "q": "Net debt was Rs 40 crore"})

    provider = MockProvider(respond)
    results = await judge_entailment_batch("Net debt is Rs 40 crore", PASSAGES, provider)
    assert [r.verdict.value for r in results] == ["unsupported", "supported"]
    assert tasks(provider) == ["verify_entailment_batch", "verify_entailment"]


async def test_verify_entries_uses_one_entailment_call_for_two_cited_chunks() -> None:
    provider = judge_provider(supports=lambda s, p: "Rs 40 crore" in p)
    entry = NotebookEntry(
        entry_id="E1",
        statement="Net debt is about Rs 40 crore",
        citations=[Citation(chunk_id=c.chunk_id, doc_id="D1", page_no=c.page_no) for c in (A, B)],
    )
    ctx = VerifyContext(
        provider=provider, chunks_by_id={c.chunk_id: c for c in (A, B)}, store=None, embedder=None
    )
    facts, dropped = await verify_entries([entry], ctx, check_relevance=False)
    assert not dropped
    assert tasks(provider) == ["verify_entailment_batch"]
    assert [c.chunk_id for c in facts[0].citations] == [A.chunk_id, B.chunk_id]
    assert all(
        c.quote in {A.chunk_id: A.text, B.chunk_id: B.text}[c.chunk_id] for c in facts[0].citations
    )


TABLE = make_chunk("D1:p3:c0", "[TABLE: Particulars | FY25]\nEBITDA | 120.5\n[/TABLE]")
PROSE = make_chunk("D1:p4:c0", "EBITDA was Rs 120.5 crore in FY25.")


def score_ctx(provider: MockProvider, kind: DocumentKind) -> VerifyContext:
    return VerifyContext(
        provider=provider,
        chunks_by_id={c.chunk_id: c for c in (TABLE, PROSE)},
        store=None,
        embedder=None,
        doc_kinds={"D1": kind},
        score_keywords=("ebitda", "net debt"),
    )


def entry_citing(entry_id: str, statement: str, chunk_id: str) -> NotebookEntry:
    cite = Citation(chunk_id=chunk_id, doc_id="D1", page_no=1)
    return NotebookEntry(entry_id=entry_id, statement=statement, citations=[cite])


async def test_table_score_input_entry_skips_relevance() -> None:
    from busybee.verify.verify_entries import is_score_input_candidate

    kind = DocumentKind.financial_statements
    ctx = score_ctx(judge_provider(), kind)
    assert is_score_input_candidate(entry_citing("E1", "EBITDA was 120.5", TABLE.chunk_id), ctx)
    assert not is_score_input_candidate(entry_citing("E2", "Revenue was 9", TABLE.chunk_id), ctx)
    assert not is_score_input_candidate(entry_citing("E3", "EBITDA was 120.5", PROSE.chunk_id), ctx)
    other = score_ctx(judge_provider(), DocumentKind.news)
    assert not is_score_input_candidate(
        entry_citing("E4", "EBITDA was 120.5", TABLE.chunk_id), other
    )


async def test_skipped_entry_is_kept_without_a_relevance_call() -> None:
    provider = judge_provider(is_relevant=lambda i: False)
    ctx = score_ctx(provider, DocumentKind.annual_report)
    entries = [
        entry_citing("E1", "EBITDA | 120.5", TABLE.chunk_id),
        entry_citing("E2", "EBITDA was Rs 120.5 crore in FY25.", PROSE.chunk_id),
    ]
    facts, dropped = await verify_entries(entries, ctx)
    assert [f.source_entry_id for f in facts] == ["E1"]
    assert [d.entry.entry_id for d in dropped] == ["E2"]
    relevance_calls = [c for c in provider.calls if c["task"] == "verify_relevance"]
    assert len(relevance_calls) == 1
    listing = relevance_calls[0]["messages"][-1].content.split("Decide on exactly")[1]
    assert "E1" not in listing
    assert REASON_SCORE_INPUT == "score input candidate"
