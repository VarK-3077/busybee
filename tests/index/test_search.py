"""Ranking, document-kind filtering, batching, and citation lookup for vector search."""

from pathlib import Path

import numpy as np

from busybee.index.embedder.hashing import HashingEmbedder
from busybee.index.search import batch_search, get_chunk, search
from busybee.index.store import VectorStore
from busybee.schema.documents import Chunk, DocumentKind

CHUNKS = [
    Chunk(
        chunk_id="D1:p1:c0",
        doc_id="D1",
        page_no=1,
        index_in_page=0,
        text="Net debt declined and liquidity improved.",
    ),
    Chunk(
        chunk_id="D2:p1:c0",
        doc_id="D2",
        page_no=1,
        index_in_page=0,
        text="Revenue growth accelerated on new orders.",
    ),
    Chunk(
        chunk_id="D3:p1:c0",
        doc_id="D3",
        page_no=1,
        index_in_page=0,
        text="The covenant limits net debt to two times EBITDA.",
    ),
]
DOC_KINDS = {"D1": "annual_report", "D2": "news", "D3": "covenant"}


async def make_store() -> VectorStore:
    embedder = HashingEmbedder()
    vectors = await embedder.embed([chunk.text for chunk in CHUNKS])
    store = VectorStore(
        vectors=np.zeros((0, embedder.dim), dtype=np.float32),
        doc_kinds=DOC_KINDS,
    )
    store.add(CHUNKS, vectors)
    return store


async def test_search_returns_the_chunk_with_the_query_words_first() -> None:
    results = await search(await make_store(), HashingEmbedder(), "covenant ebitda", k=3)
    assert results[0].chunk.chunk_id == "D3:p1:c0"
    assert results[0].score > results[1].score


async def test_search_respects_k() -> None:
    results = await search(await make_store(), HashingEmbedder(), "net debt", k=1)
    assert len(results) == 1


async def test_search_filters_by_document_kind() -> None:
    results = await search(
        await make_store(),
        HashingEmbedder(),
        "net debt",
        k=5,
        doc_kinds=[DocumentKind.news],
    )
    assert len(results) == 1
    assert results[0].chunk.doc_id == "D2"


async def test_search_accepts_a_single_kind_string() -> None:
    results = await search(
        await make_store(), HashingEmbedder(), "net debt", k=5, doc_kinds="covenant"
    )
    assert [result.chunk.chunk_id for result in results] == ["D3:p1:c0"]


async def test_search_with_no_matching_kind_is_empty() -> None:
    results = await search(
        await make_store(), HashingEmbedder(), "net debt", doc_kinds=["bank_statement"]
    )
    assert results == []


async def test_search_accepts_an_index_directory(tmp_path: Path) -> None:
    directory = (await make_store()).save(tmp_path / "index")
    results = await search(directory, HashingEmbedder(), "covenant ebitda", k=1)
    assert results[0].chunk.chunk_id == "D3:p1:c0"


async def test_search_on_an_empty_store_is_empty() -> None:
    store = VectorStore(vectors=np.zeros((0, 256), dtype=np.float32))
    assert await search(store, HashingEmbedder(), "anything") == []


async def test_search_with_non_positive_k_is_empty() -> None:
    assert await search(await make_store(), HashingEmbedder(), "net debt", k=0) == []


async def test_batch_search_returns_one_ranking_per_query() -> None:
    results = await batch_search(
        await make_store(), HashingEmbedder(), ["covenant ebitda", "revenue growth"], k=1
    )
    assert [[item.chunk.chunk_id for item in ranking] for ranking in results] == [
        ["D3:p1:c0"],
        ["D2:p1:c0"],
    ]


async def test_batch_search_empty_queries() -> None:
    assert await batch_search(await make_store(), HashingEmbedder(), [], k=1) == []


def test_get_chunk_returns_the_citation_target() -> None:
    store = VectorStore(
        vectors=np.zeros((0, 4), dtype=np.float32),
        chunks=list(CHUNKS),
        meta=[
            {"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "page_no": 1, "kind": "news"}
            for chunk in CHUNKS
        ],
    )
    assert get_chunk(store, "D2:p1:c0") == CHUNKS[1]


def test_get_chunk_returns_none_for_a_missing_id() -> None:
    store = VectorStore(
        vectors=np.zeros((0, 4), dtype=np.float32),
        chunks=list(CHUNKS),
    )
    assert get_chunk(store, "D9:p9:c9") is None
