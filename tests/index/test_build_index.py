"""End-to-end indexing of a tiny hand-written corpus in a temporary workspace."""

from pathlib import Path

import numpy as np

from busybee.index import HashingEmbedder, VectorStore, run_index, search
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.io import append_jsonl, write_models_atomic


def write_corpus(workspace: Path) -> None:
    corpus = workspace / "corpus"
    documents = [
        Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report),
        Document(doc_id="D2", title="News", kind=DocumentKind.news),
        Document(doc_id="D3", title="Covenant Sheet", kind=DocumentKind.covenant),
    ]
    chunks = [
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
    write_models_atomic(corpus / "documents.json", documents)
    for chunk in chunks:
        append_jsonl(corpus / "chunks.jsonl", chunk)


async def test_run_index_builds_a_searchable_index(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    write_corpus(workspace)
    store = await run_index(workspace, HashingEmbedder())

    assert (workspace / "index" / "vectors.npy").exists()
    assert (workspace / "index" / "meta.jsonl").exists()
    assert (workspace / "index" / "chunks.jsonl").exists()
    assert len(store) == 3
    assert store.vectors.shape == (3, 256)
    assert store.doc_kinds["D3"] == "covenant"

    loaded = VectorStore.load(workspace / "index")
    results = await search(loaded, HashingEmbedder(), "covenant ebitda", k=1)
    assert results[0].chunk.chunk_id == "D3:p1:c0"


async def test_run_index_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    write_corpus(workspace)
    first = await run_index(workspace, HashingEmbedder())
    second = await run_index(workspace, HashingEmbedder())
    assert np.array_equal(first.vectors, second.vectors)
    assert first.chunks == second.chunks
    assert first.meta == second.meta


async def test_run_index_defaults_to_the_offline_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("BUSYBEE_EMBED_PROVIDER", raising=False)
    workspace = tmp_path / "run"
    write_corpus(workspace)
    store = await run_index(workspace)
    assert store.vectors.shape == (3, 256)


async def test_run_index_on_an_empty_corpus(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    corpus = workspace / "corpus"
    write_models_atomic(corpus / "documents.json", [])
    (corpus / "chunks.jsonl").write_text("", encoding="utf-8")
    store = await run_index(workspace, HashingEmbedder())
    assert len(store) == 0
    assert store.vectors.shape == (0, 256)
    assert (workspace / "index" / "vectors.npy").exists()


async def test_embedded_text_includes_the_table_prefix() -> None:
    from busybee.index.build_index import _embed_chunks

    seen: list[str] = []

    class Spy:
        dim = 2

        async def embed(self, texts: list[str]) -> np.ndarray:
            seen.extend(texts)
            return np.zeros((len(texts), 2), dtype=np.float32)

    chunk = Chunk(
        chunk_id="D1:p1:c1",
        doc_id="D1",
        page_no=1,
        index_in_page=1,
        text="Revenue | 100",
        prefix="[TABLE: item | crore]",
    )
    await _embed_chunks(Spy(), [chunk])
    assert seen == ["[TABLE: item | crore]\nRevenue | 100"]
