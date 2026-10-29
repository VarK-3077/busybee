"""Tests for atomic JSON writes, model helpers, and JSONL append/read."""

import json
from pathlib import Path

import pytest

from busybee.schema.documents import Chunk
from busybee.schema.io import (
    append_jsonl,
    read_json,
    read_jsonl,
    read_model,
    read_models,
    write_json_atomic,
    write_model_atomic,
    write_models_atomic,
)


def sample_chunk(index: int) -> Chunk:
    return Chunk(
        chunk_id=f"D1:p1:c{index}",
        doc_id="D1",
        page_no=1,
        index_in_page=index,
        text=f"chunk {index}",
        char_start=index * 10,
        char_end=index * 10 + 9,
    )


def test_write_and_read_json_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "data.json"
    data = {"company": "Acme", "numbers": [1, 2.5, None], "flag": True}
    write_json_atomic(path, data)
    assert read_json(path) == data
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_write_and_read_one_model(tmp_path: Path) -> None:
    path = tmp_path / "chunk.json"
    chunk = sample_chunk(0)
    write_model_atomic(path, chunk)
    assert read_model(path, Chunk) == chunk


def test_write_and_read_many_models(tmp_path: Path) -> None:
    path = tmp_path / "chunks.json"
    chunks = [sample_chunk(0), sample_chunk(1)]
    write_models_atomic(path, chunks)
    assert read_models(path, Chunk) == chunks


def test_atomic_write_leaves_no_temp_file_on_success(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    write_json_atomic(path, {"ok": True})
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()


def test_failed_write_leaves_no_partial_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    with pytest.raises(TypeError):
        write_json_atomic(path, {"unserialisable": object()})
    assert not path.exists()
    assert not path.with_suffix(".json.tmp").exists()


def test_atomic_write_replaces_existing_content(tmp_path: Path) -> None:
    path = tmp_path / "replace.json"
    write_json_atomic(path, {"version": 1})
    write_json_atomic(path, {"version": 2})
    assert read_json(path) == {"version": 2}


def test_jsonl_append_and_read(tmp_path: Path) -> None:
    path = tmp_path / "notebook.jsonl"
    first = sample_chunk(0)
    second = sample_chunk(1)
    append_jsonl(path, first)
    append_jsonl(path, second)
    assert read_jsonl(path, Chunk) == [first, second]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_jsonl_read_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "missing.jsonl", Chunk) == []
