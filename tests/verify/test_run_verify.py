"""run_verify end to end on a tiny workspace: ids, output files, appended dropped list."""

from pathlib import Path

from busybee.ingest.corpus_store import write_corpus
from busybee.schema.documents import Document, DocumentKind, Page
from busybee.schema.facts import DroppedEntry, NotebookEntry, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.run import RunConfig
from busybee.verify.run_verify import run_verify

from .helpers import judge_provider, make_chunk, make_entry

CHUNK = make_chunk("D1:p1:c0", "Revenue for FY24 was Rs 1,200 crore.")


async def test_run_verify_writes_outputs(tmp_path: Path) -> None:
    document = Document(
        doc_id="D1",
        title="AR",
        kind=DocumentKind.annual_report,
        source_path="x",
        sha256="0",
        num_pages=1,
    )
    write_corpus(
        tmp_path, [document], {"D1": [Page(doc_id="D1", page_no=1, text=CHUNK.text)]}, [CHUNK]
    )
    entries = [
        make_entry("E1", "Revenue for FY24 was Rs 1,200 crore"),
        make_entry("E2", "Irrelevant trivia"),
    ]
    write_models_atomic(tmp_path / "notebook.json", entries)
    earlier = DroppedEntry(
        entry=NotebookEntry(entry_id="X", statement="old"), reason="r", stage="extract"
    )
    write_models_atomic(tmp_path / "dropped.json", [earlier])
    cfg = RunConfig(
        run_id="r", docs_dir=tmp_path, bank_id="b", out_dir=tmp_path, workspace_dir=tmp_path
    )

    facts = await run_verify(tmp_path, cfg, judge_provider(is_relevant=lambda i: i == "E1"))

    assert [f.fact_id for f in facts] == ["F001"]
    saved = read_models(tmp_path / "verified_facts.json", VerifiedFact)
    assert saved[0].source_entry_id == "E1"
    dropped = read_models(tmp_path / "dropped.json", DroppedEntry)
    assert [d.entry.entry_id for d in dropped] == ["X", "E2"]


async def test_run_verify_merges_duplicate_facts_before_numbering(tmp_path: Path) -> None:
    document = Document(
        doc_id="D1",
        title="AR",
        kind=DocumentKind.annual_report,
        source_path="x",
        sha256="0",
        num_pages=1,
    )
    write_corpus(
        tmp_path, [document], {"D1": [Page(doc_id="D1", page_no=1, text=CHUNK.text)]}, [CHUNK]
    )
    entries = [
        make_entry("E1", "Revenue for FY24 was Rs 1,200 crore"),
        make_entry("E2", "revenue for FY24 was Rs 1,200 crore."),
    ]
    write_models_atomic(tmp_path / "notebook.json", entries)
    cfg = RunConfig(
        run_id="r", docs_dir=tmp_path, bank_id="b", out_dir=tmp_path, workspace_dir=tmp_path
    )
    facts = await run_verify(tmp_path, cfg, judge_provider())

    assert [f.fact_id for f in facts] == ["F001"]
    assert facts[0].verification is not None
    assert "E2" in facts[0].verification.notes


async def test_run_verify_marks_cross_document_conflict_and_writes_conflicts_json(
    tmp_path: Path,
) -> None:
    import json

    from busybee.llm import MockProvider
    from busybee.schema.report import Concern

    documents = [
        Document(doc_id="D1", title="Audited", kind=DocumentKind.financial_statements),
        Document(doc_id="D2", title="Press", kind=DocumentKind.news),
    ]
    chunks = [
        make_chunk("D1:p1:c0", "Revenue from operations was INR 931.2 crore in FY25."),
        make_chunk("D2:p1:c0", "The company closed FY25 with revenue of Rs 1,018 crore."),
    ]
    pages = {c.doc_id: [Page(doc_id=c.doc_id, page_no=1, text=c.text)] for c in chunks}
    write_corpus(tmp_path, documents, pages, chunks)
    write_models_atomic(
        tmp_path / "notebook.json",
        [
            make_entry("E1", "Revenue from operations was INR 931.2 crore in FY25"),
            make_entry("E2", "The company closed FY25 with revenue of Rs 1,018 crore", "D2:p1:c0"),
        ],
    )
    cfg = RunConfig(
        run_id="r", docs_dir=tmp_path, bank_id="b", out_dir=tmp_path, workspace_dir=tmp_path
    )
    base = judge_provider()

    def respond(messages: list, task: str) -> str:
        if task == "verify_conflict":
            return json.dumps(
                {"results": [{"pair": 1, "conflict": True, "metric": "revenue", "note": "n"}]}
            )
        return base.responses(messages, task)  # type: ignore[operator]

    await run_verify(tmp_path, cfg, MockProvider(respond))

    saved = {f.fact_id: f for f in read_models(tmp_path / "verified_facts.json", VerifiedFact)}
    assert saved["F002"].verification is not None
    assert saved["F002"].verification.status.value == "conflicted"
    assert [n.fact_id for n in saved["F001"].conflicts] == ["F002"]
    [concern] = read_models(tmp_path / "conflicts.json", Concern)
    assert concern.fact_ids == ["F001", "F002"]
