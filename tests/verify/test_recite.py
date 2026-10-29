"""Re-citation searches the hashing-embedder store and returns the first supporting chunk."""

from busybee.verify.recite import recite

from .helpers import judge_provider, make_chunk, make_store

CHUNKS = [
    make_chunk("D1:p1:c0", "The board met four times during the year."),
    make_chunk("D1:p2:c0", "Net debt stood at Rs 40 crore at year end."),
    make_chunk("D2:p1:c0", "Net debt of Rs 45 crore was reported by a peer."),
]


async def test_recite_finds_supporting_chunk() -> None:
    store, embedder = await make_store(CHUNKS)
    provider = judge_provider(supports=lambda s, p: "40 crore" in p)
    found = await recite("Net debt stood at Rs 40 crore", store, embedder, provider)
    assert found is not None
    assert found.chunk.chunk_id == "D1:p2:c0"
    assert found.quote


async def test_recite_skips_chunks_missing_the_numbers_without_llm_calls() -> None:
    store, embedder = await make_store(CHUNKS)
    provider = judge_provider()
    found = await recite("Net debt stood at Rs 99 crore", store, embedder, provider)
    assert found is None
    assert provider.calls == []


async def test_recite_returns_none_when_nothing_supports() -> None:
    store, embedder = await make_store(CHUNKS)
    provider = judge_provider(supports=lambda s, p: False)
    assert await recite("Net debt stood at Rs 40 crore", store, embedder, provider) is None


async def test_recite_honours_exclusions() -> None:
    store, embedder = await make_store(CHUNKS)
    provider = judge_provider(supports=lambda s, p: True)
    found = await recite(
        "Net debt stood at Rs 40 crore", store, embedder, provider, exclude_chunk_ids={"D1:p2:c0"}
    )
    assert found is None
