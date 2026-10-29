"""verify_entries with BUSYBEE_JUDGE=classifier / tiered through a fake sidecar transport."""

import pytest

from busybee.verify.judge import judge_from_env
from busybee.verify.verify_entries import VerifyContext, verify_entries

from .helpers import judge_provider, make_chunk, make_entry
from .test_judge import sidecar

LONG = (
    "Header line\n"
    + "\n".join(f"filler row {i}" for i in range(300))
    + ("\nTotal borrowings were Rs 300 crore at 31 March 2024.\nTail line")
)
CHUNKS = [
    make_chunk("D1:p1:c0", "Company overview.\nRevenue for FY24 was Rs 1,200 crore, up 12%."),
    make_chunk("D1:p2:c0", LONG),
]


def ctx_for(provider, transport) -> VerifyContext:  # noqa: ANN001
    return VerifyContext(
        provider=provider,
        chunks_by_id={c.chunk_id: c for c in CHUNKS},
        store=None,
        embedder=None,
        judge=judge_from_env(provider, transport=transport),
    )


async def test_classifier_decides_with_deterministic_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_JUDGE", "classifier")
    seen: list[tuple[str, dict]] = []
    provider = judge_provider(supports=lambda s, p: False)
    entries = [
        make_entry("E1", "FY24 revenue grew to Rs 1,200 crore", "D1:p1:c0"),
        make_entry("E2", "Borrowings stood at Rs 300 crore in March 2024", "D1:p2:c0"),
        make_entry("E3", "Revenue was Rs 1,200 crore in FY24 and unrelated claims", "D1:p1:c0"),
    ]
    transport = sidecar(lambda s, p: 0.1 if "unrelated" in s else 0.95, seen)
    facts, dropped = await verify_entries(
        entries, ctx_for(provider, transport), check_relevance=False
    )
    assert [f.source_entry_id for f in facts] == ["E1", "E2"]
    assert all(f.verification.method == "classifier_entailment" for f in facts)
    quotes = {f.source_entry_id: f.citations[0].quote for f in facts}
    assert quotes["E1"] == "Revenue for FY24 was Rs 1,200 crore, up 12%."
    assert quotes["E2"] == "Total borrowings were Rs 300 crore at 31 March 2024."
    for fact in facts:
        assert fact.citations[0].quote in CHUNKS[int(fact.citations[0].chunk_id[4]) - 1].text
    assert dropped[0].entry.entry_id == "E3" and "judge prob 0.10" in dropped[0].reason
    long_pass = [p["passage"] for path, b in seen if path == "/entail" for p in b["pairs"]]
    assert max(len(p) for p in long_pass) <= 1500


async def test_tiered_band_uses_llm_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_JUDGE", "tiered")
    provider = judge_provider(supports=lambda s, p: True)
    entry = make_entry("E1", "FY24 revenue grew to Rs 1,200 crore", "D1:p1:c0")
    facts, _ = await verify_entries(
        [entry], ctx_for(provider, sidecar(lambda s, p: 0.5)), check_relevance=False
    )
    assert facts[0].verification.method == "tiered_entailment"
    assert facts[0].citations[0].quote in CHUNKS[0].text


async def test_classifier_relevance_drops_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_JUDGE", "classifier")
    monkeypatch.setenv("BUSYBEE_JUDGE_RELEVANCE", "classifier")
    provider = judge_provider(supports=lambda s, p: True)
    ctx = ctx_for(provider, sidecar())
    ctx = VerifyContext(**{**ctx.__dict__, "required_inputs": "- revenue: Revenue"})
    entries = [
        make_entry("E1", "Revenue for FY24 was Rs 1,200 crore", "D1:p1:c0"),
        make_entry("E2", "The board met four times", "D1:p1:c0"),
    ]
    facts, dropped = await verify_entries(entries, ctx)
    assert [f.source_entry_id for f in facts] == ["E1"]
    assert dropped[0].entry.entry_id == "E2"
    assert dropped[0].stage == "verify.relevance" and "classifier relevance" in dropped[0].reason
