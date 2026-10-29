"""Determinism, shape, and normalisation tests for the offline hashing embedder."""

import numpy as np

from busybee.index.embedder.hashing import HashingEmbedder


async def test_hashing_embedder_is_deterministic_across_instances() -> None:
    first = await HashingEmbedder().embed(["Net debt declined", "Revenue grew"])
    second = await HashingEmbedder().embed(["Net debt declined", "Revenue grew"])
    assert np.array_equal(first, second)


async def test_hashing_embedder_returns_normalised_float32_rows() -> None:
    embedder = HashingEmbedder()
    vectors = await embedder.embed(["net debt covenant", "revenue growth", "liquidity"])
    assert vectors.dtype == np.float32
    assert vectors.shape == (3, 256)
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0)


async def test_hashing_embedder_is_case_insensitive() -> None:
    embedder = HashingEmbedder()
    lower = await embedder.embed(["net debt covenant"])
    upper = await embedder.embed(["NET DEBT COVENANT"])
    assert np.array_equal(lower, upper)


async def test_hashing_embedder_empty_text_is_a_zero_row() -> None:
    vectors = await HashingEmbedder().embed([""])
    assert vectors.shape == (1, 256)
    assert not np.any(vectors)


async def test_hashing_embedder_empty_batch_has_the_configured_width() -> None:
    vectors = await HashingEmbedder(dim=64).embed([])
    assert vectors.shape == (0, 64)
    assert vectors.dtype == np.float32


async def test_hashing_embedder_ranks_related_text_above_unrelated_text() -> None:
    vectors = await HashingEmbedder().embed(
        ["net debt covenant", "net debt covenant limits ebitda", "revenue growth"]
    )
    related = float(vectors[0] @ vectors[1])
    unrelated = float(vectors[0] @ vectors[2])
    assert related > unrelated
