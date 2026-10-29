"""String tests for the recall rules in the extract, entailment and relevance prompts."""

from busybee.extract.prompts import SYSTEM_PROMPT
from busybee.extract.rescue_citations import rescued_records
from busybee.llm import Role
from busybee.schema.facts import Citation, NotebookEntry
from busybee.verify.entailment import _SYSTEM as ENTAILMENT_SYSTEM
from busybee.verify.relevance import build_relevance_messages


def test_extract_prompt_has_rating_and_citation_rules() -> None:
    for phrase in (
        "rating-history row",
        "upgrade and downgrade triggers",
        "own metric names",
        "Never omit the chunk id",
    ):
        assert phrase in SYSTEM_PROMPT


def test_entailment_prompt_metric_and_direction_rules() -> None:
    assert "total income from operations" in ENTAILMENT_SYSTEM
    assert "operating income" in ENTAILMENT_SYSTEM
    assert "downgraded" in ENTAILMENT_SYSTEM and "match the passage literally" in ENTAILMENT_SYSTEM


def test_relevance_prompt_keeps_dividends_and_drops_admin() -> None:
    entry = NotebookEntry(entry_id="D1:E001", statement="x")
    system = next(m for m in build_relevance_messages([entry], "") if m.role is Role.system)
    for phrase in ("dividends declared or recommended", "buybacks", "book closure", "IEPF"):
        assert phrase in system.content


def test_rescued_records_lists_only_inferred_entries() -> None:
    cite = Citation(chunk_id="D1:p1:c0", doc_id="D1", page_no=1)
    inferred = NotebookEntry(
        entry_id="D1:E001", statement="a", citations=[cite], citation_inferred=True
    )
    plain = NotebookEntry(entry_id="D1:E002", statement="b", citations=[cite])
    assert [r["entry_id"] for r in rescued_records([inferred, plain])] == ["D1:E001"]
