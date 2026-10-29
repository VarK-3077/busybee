"""Round-trip and format tests for the stable identifier constructors."""

import pytest

from busybee.schema.ids import (
    make_chunk_id,
    make_concern_id,
    make_doc_id,
    make_entry_id,
    make_fact_id,
    make_inference_id,
    make_score_artifact_id,
    parse_chunk_id,
)


def test_doc_id_accepts_number_or_existing_id() -> None:
    assert make_doc_id(1) == "D1"
    assert make_doc_id(42) == "D42"
    assert make_doc_id("D7") == "D7"
    assert make_doc_id("7") == "D7"


def test_chunk_id_round_trips() -> None:
    for doc_no, page_no, index in [(1, 1, 0), (2, 214, 3), (10, 7, 12)]:
        chunk_id = make_chunk_id(doc_no, page_no, index)
        assert parse_chunk_id(chunk_id) == (f"D{doc_no}", page_no, index)


def test_chunk_id_uses_page_exact_format() -> None:
    assert make_chunk_id(1, 214, 2) == "D1:p214:c2"
    assert make_chunk_id("D3", 5, 0) == "D3:p5:c0"


@pytest.mark.parametrize("bad", ["", "D1", "D1:p2", "D1:p2:c", "X1:p2:c3", "D1:p2:c3:extra"])
def test_parse_chunk_id_rejects_malformed_ids(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_chunk_id(bad)


def test_other_identifiers() -> None:
    assert make_fact_id(1) == "F001"
    assert make_fact_id(12) == "F012"
    assert make_fact_id(1234) == "F1234"
    assert make_entry_id("D1", 1) == "D1:E001"
    assert make_entry_id("D9", 23) == "D9:E023"
    assert make_inference_id(1) == "I001"
    assert make_concern_id(7) == "C007"
    assert make_score_artifact_id("run-1", "leverage") == "run-1:leverage"
