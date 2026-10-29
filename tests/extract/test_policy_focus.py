"""Importance from the bank policy: 5 feeds a rule or score, 4 at most for the rest."""

import json
from pathlib import Path

from busybee.extract.aids import ReadingAids
from busybee.extract.per_document import extract_document
from busybee.extract.policy_focus import (
    apply_policy_importance,
    feeds_policy,
    load_policy_focus,
)
from busybee.extract.run_extract import run_extract
from busybee.llm import MockProvider
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.facts import FactRecord, NotebookEntry
from busybee.schema.io import append_jsonl, read_models, write_models_atomic
from busybee.schema.run import RunConfig

BANKS = Path(__file__).parents[2] / "banks"
FOCUS = load_policy_focus(BANKS, "demo_bank")


def entry(statement: str, importance: int = 3, metric: str | None = None) -> NotebookEntry:
    record = FactRecord(metric=metric, value=1) if metric else None
    return NotebookEntry(
        entry_id="D1:E001", statement=statement, importance=importance, record=record
    )


def test_focus_loads_from_the_bank_and_missing_bank_gives_none() -> None:
    assert FOCUS is not None and "Credit-policy checklist" in FOCUS.checklist
    assert load_policy_focus(BANKS, "no_such_bank") is None
    assert load_policy_focus(None, "demo_bank") is None


def test_records_that_match_a_score_input_feed_the_policy() -> None:
    assert FOCUS is not None
    for metric in (
        "Borrowings",
        "Total Equity",
        "Revenue from Operations (Net of Returns)",
        "Finance Costs",
        "Cash and Cash Equivalents",
        "Total Current Assets",
        "Lease Liabilities (Current)",
        "Income tax paid (net of refunds)",
    ):
        assert feeds_policy(entry("x", metric=metric), FOCUS), metric
    for metric in (
        "Other Current Liabilities",
        "Operating Profit Margin (%)",
        "Gross wages paid to females",
        "Trade Receivables",
    ):
        assert not feeds_policy(entry("x", metric=metric), FOCUS), metric


def test_red_flag_keywords_and_rating_grades_feed_the_policy() -> None:
    assert FOCUS is not None
    assert feeds_policy(entry("The auditors issued a qualified opinion on the accounts."), FOCUS)
    assert feeds_policy(entry("USFDA issued a Form 483 with 7 observations."), FOCUS)
    assert feeds_policy(
        entry("ICRA reaffirmed the long-term rating at [ICRA]A- (Negative)."), FOCUS
    )
    assert not feeds_policy(entry("The company runs a CSR programme in a village."), FOCUS)
    assert not feeds_policy(entry("A new plant was commissioned in Goa."), FOCUS)


def test_importance_is_five_for_policy_facts_and_capped_at_four_otherwise() -> None:
    entries = [
        entry("a", importance=2, metric="Borrowings"),
        entry("b", importance=5),
        entry("c", importance=4),
        entry("d", importance=3),
        entry("The Group has no wilful default.", importance=1),
    ]
    result = apply_policy_importance(entries, FOCUS)
    assert [e.importance for e in result] == [5, 4, 4, 3, 5]
    assert [e.importance for e in apply_policy_importance(entries, None)] == [2, 5, 4, 3, 1]


def response(statement: str, chunk_id: str, importance: int) -> str:
    entry_ = {
        "statement": statement,
        "chunk_ids": [chunk_id],
        "category": "debt_leverage",
        "kind": "number",
        "importance": importance,
    }
    return json.dumps({"entries": [entry_]})


def config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_id="t",
        docs_dir=tmp_path,
        bank_id="demo_bank",
        out_dir=tmp_path,
        workspace_dir=tmp_path / "workspace",
        window_tokens=10_000,
    )


async def test_extract_document_applies_policy_importance_without_a_calibrate_call(
    tmp_path: Path,
) -> None:
    chunk = Chunk(
        chunk_id="D1:p1:c0", doc_id="D1", page_no=1, index_in_page=0, text="Borrowings were 5."
    )
    doc = Document(doc_id="D1", title="AR", kind=DocumentKind.annual_report)
    provider = MockProvider(
        {"extract": [response("Borrowings were INR 5 crore.", chunk.chunk_id, 3)]}
    )
    entries = await extract_document(
        doc, [chunk], config(tmp_path), provider, aids=ReadingAids(focus=FOCUS)
    )
    assert [call.task for call in provider.calls] == ["extract"]
    assert [e.importance for e in entries] == [5]


async def test_run_extract_loads_the_bank_from_banks_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    doc = Document(doc_id="D1", title="AR", kind=DocumentKind.annual_report)
    chunk = Chunk(
        chunk_id="D1:p1:c0", doc_id="D1", page_no=1, index_in_page=0, text="Plant commissioned."
    )
    write_models_atomic(workspace / "corpus" / "documents.json", [doc])
    append_jsonl(workspace / "corpus" / "chunks.jsonl", chunk)
    provider = MockProvider({"extract": [response("A plant was commissioned.", chunk.chunk_id, 5)]})
    await run_extract(workspace, config(tmp_path), provider, BANKS)
    assert [e.importance for e in read_models(workspace / "notebook.json", NotebookEntry)] == [4]
