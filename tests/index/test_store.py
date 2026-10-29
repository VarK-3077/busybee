"""Save/load round trips and validation for the on-disk vector store."""

from pathlib import Path

import numpy as np
import pytest

from busybee.index.store import VectorStore, load_store, save_store
from busybee.schema.documents import Chunk


def sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="D1:p1:c0",
            doc_id="D1",
            page_no=1,
            index_in_page=0,
            text="Net debt declined and liquidity improved.",
            char_start=0,
            char_end=36,
        ),
        Chunk(
            chunk_id="D2:p1:c0",
            doc_id="D2",
            page_no=1,
            index_in_page=0,
            text="Revenue growth accelerated on new orders.",
            char_start=0,
            char_end=40,
        ),
    ]


def sample_store() -> VectorStore:
    chunks = sample_chunks()
    store = VectorStore(
        vectors=np.zeros((0, 4), dtype=np.float32),
        doc_kinds={"D1": "annual_report", "D2": "news"},
    )
    store.add(chunks, np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32))
    return store


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    store = sample_store()
    store.save(tmp_path / "index")
    loaded = VectorStore.load(tmp_path / "index")
    assert loaded.chunks == store.chunks
    assert loaded.meta == store.meta
    assert loaded.doc_kinds == store.doc_kinds
    assert np.array_equal(loaded.vectors, store.vectors)


def test_meta_records_the_document_kind(tmp_path: Path) -> None:
    store = sample_store()
    store.save(tmp_path / "index")
    loaded = VectorStore.load(tmp_path / "index")
    assert loaded.meta == [
        {"chunk_id": "D1:p1:c0", "doc_id": "D1", "page_no": 1, "kind": "annual_report"},
        {"chunk_id": "D2:p1:c0", "doc_id": "D2", "page_no": 1, "kind": "news"},
    ]


def test_add_appends_vectors_and_chunks(tmp_path: Path) -> None:
    store = sample_store()
    extra = Chunk(
        chunk_id="D3:p2:c0",
        doc_id="D3",
        page_no=2,
        index_in_page=0,
        text="The covenant limits net debt.",
    )
    store.add([extra], np.array([[0.0, 0.0, 1.0, 0.0]], dtype=np.float32))
    assert len(store) == 3
    assert store.chunks[-1] == extra
    assert store.meta[-1]["kind"] == "other"
    assert store.vectors.shape == (3, 4)


def test_add_rejects_misaligned_vectors() -> None:
    store = sample_store()
    with pytest.raises(ValueError):
        store.add(sample_chunks(), np.zeros((1, 4), dtype=np.float32))


def test_add_rejects_a_different_dimension() -> None:
    store = sample_store()
    with pytest.raises(ValueError):
        store.add(sample_chunks(), np.zeros((2, 8), dtype=np.float32))


def test_save_leaves_no_temporary_files(tmp_path: Path) -> None:
    directory = sample_store().save(tmp_path / "index")
    assert not list(directory.glob("*.tmp"))


def test_empty_store_round_trip(tmp_path: Path) -> None:
    store = VectorStore(vectors=np.zeros((0, 8), dtype=np.float32))
    store.save(tmp_path / "index")
    loaded = VectorStore.load(tmp_path / "index")
    assert len(loaded) == 0
    assert loaded.vectors.shape == (0, 8)


def test_module_level_helpers(tmp_path: Path) -> None:
    store = sample_store()
    save_store(store, tmp_path / "index")
    loaded = load_store(tmp_path / "index")
    assert loaded.chunks == store.chunks


def test_load_rejects_unaligned_files(tmp_path: Path) -> None:
    store = sample_store()
    directory = store.save(tmp_path / "index")
    (directory / "meta.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        VectorStore.load(directory)


def test_chunks_by_id() -> None:
    lookup = sample_store().chunks_by_id()
    assert lookup["D1:p1:c0"].text.startswith("Net debt")
