"""Boilerplate page skipping: title runs, protected pages, the run_extract wiring."""

import json
from pathlib import Path

from busybee.extract.boilerplate import (
    configured_titles,
    drop_boilerplate,
    enabled,
    skipped_pages,
)
from busybee.extract.run_extract import SKIPPED_FILE, run_extract
from busybee.llm import MockProvider
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.io import append_jsonl, write_models_atomic
from busybee.schema.run import RunConfig

PAGES = {
    1: "Annual Report\nRevenue was INR 931.2 crore in FY25.",
    2: "INDOCO LIMITED\n[CIN: L1]\nRegistered Office: Mumbai\nN O T I C E\nNotice is hereby given",
    3: "RESOLVED THAT the borrowings are approved.",
    4: "Annexure -1\nProfile of Directors\nDetails of the Directors seeking re-appointment",
    5: "DIRECTORS’ REPORT\nDear Members, results from operations",
    6: "Annexure-C\nto the Directors’ Report\nAnnual Report on Corporate Social Responsibility",
    7: "Whether CSR is applicable: yes",
    8: "Annexure-E\nto the Directors’ Report\nForm AOC-2\nRelated party transactions",
    9: "Report on Corporate Governance for the year ended March 31, 2026\nPhilosophy",
    10: "Attendance of directors\nBalance Sheet\nTotal assets | 100",
    11: "Management Discussion and Analysis\nIndustry overview",
    12: "BUSINESS RESPONSIBILITY & SUSTAINABILITY REPORT\nSECTION A",
    13: "Independent Auditors’ Report\nOpinion",
    14: "Other information\nBusiness Responsibility and Sustainability",
}


def chunks_of(doc_id: str = "D1") -> list[Chunk]:
    return [
        Chunk(chunk_id=f"{doc_id}:p{n}:c0", doc_id=doc_id, page_no=n, index_in_page=0, text=text)
        for n, text in PAGES.items()
    ]


def test_runs_start_at_a_title_and_stop_at_a_report_heading() -> None:
    assert skipped_pages(chunks_of()) == [2, 3, 4, 6, 7, 9, 12]


def test_pages_with_financial_statements_are_never_skipped() -> None:
    skipped = skipped_pages(chunks_of())
    assert 10 not in skipped and 11 not in skipped and 13 not in skipped and 14 not in skipped


def test_notice_annexures_stay_in_the_run_but_report_annexures_end_it() -> None:
    skipped = skipped_pages(chunks_of())
    assert 4 in skipped and 8 not in skipped


def test_extra_titles_come_from_the_environment() -> None:
    titles = configured_titles({"BUSYBEE_BOILERPLATE_TITLES": "^photo gallery; ^awards"})
    assert titles[-2:] == ("^photo gallery", "^awards")
    assert enabled({}) and not enabled({"BUSYBEE_SKIP_BOILERPLATE": "0"})
    extra = [Chunk(chunk_id="D1:p1:c0", doc_id="D1", page_no=1, index_in_page=0, text="Awards\nx")]
    assert skipped_pages(extra) == []
    assert skipped_pages(extra, titles) == [1]


def test_only_annual_reports_are_filtered() -> None:
    annual = Document(doc_id="D1", title="AR", kind=DocumentKind.annual_report)
    news = Document(doc_id="D2", title="News", kind=DocumentKind.news)
    by_doc = {"D1": chunks_of("D1"), "D2": chunks_of("D2")}
    kept, skipped = drop_boilerplate([annual, news], by_doc)
    assert set(skipped) == {"D1"}
    assert len(kept["D1"]) == len(by_doc["D1"]) - 7 and kept["D2"] == by_doc["D2"]


async def test_run_extract_never_shows_skipped_pages_to_the_model(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    doc = Document(doc_id="D1", title="AR", kind=DocumentKind.annual_report, source_path="a.md")
    corpus = workspace / "corpus"
    write_models_atomic(corpus / "documents.json", [doc])
    for chunk in chunks_of():
        append_jsonl(corpus / "chunks.jsonl", chunk)
    provider = MockProvider({"extract": [json.dumps({"entries": []})] * 20})
    cfg = RunConfig(
        run_id="t",
        docs_dir=tmp_path,
        bank_id="b",
        out_dir=tmp_path,
        workspace_dir=workspace,
        window_tokens=10_000,
    )
    await run_extract(workspace, cfg, provider)
    shown = "".join(m.content for call in provider.calls for m in call.messages)
    assert "D1:p3:c0" not in shown and "D1:p5:c0" in shown
    assert json.loads((workspace / SKIPPED_FILE).read_text()) == {"D1": [2, 3, 4, 6, 7, 9, 12]}
