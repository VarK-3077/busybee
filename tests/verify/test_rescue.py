"""rescue_dropped: re-judge relevance drops, append new facts, reset downstream stages."""

from pathlib import Path

from busybee.ingest.corpus_store import write_corpus
from busybee.schema.documents import Document, DocumentKind, Page
from busybee.schema.facts import DroppedEntry, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.run import RunConfig, StageState, StageStatus
from busybee.verify.rescue import rescue_dropped
from busybee.verify.verify_entries import STAGE_CITATION, STAGE_RELEVANCE

from .helpers import judge_provider, make_chunk, make_entry

CHUNK = make_chunk("D1:p1:c0", "Revenue was Rs 1,200 crore. Promoters hold 52% of the company.")


def _workspace(tmp_path: Path) -> RunConfig:
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
    existing = VerifiedFact(
        fact_id="F001", statement="Revenue was Rs 1,200 crore.", source_entry_id="E1"
    )
    write_models_atomic(tmp_path / "verified_facts.json", [existing])
    entries = [
        make_entry("E1", "Revenue was Rs 1,200 crore."),
        make_entry("E2", "Promoters hold 52% of the company."),
        make_entry("E3", "Promoters hold 99% of the company."),
    ]
    write_models_atomic(tmp_path / "notebook.json", entries)
    write_models_atomic(
        tmp_path / "dropped.json",
        [
            DroppedEntry(entry=entries[1], reason="not relevant: x", stage=STAGE_RELEVANCE),
            DroppedEntry(entry=entries[2], reason="not relevant: x", stage=STAGE_RELEVANCE),
            DroppedEntry(entry=make_entry("E9", "old"), reason="bad cite", stage=STAGE_CITATION),
        ],
    )
    write_models_atomic(
        tmp_path / "stages.json",
        [StageStatus(name=n, state=StageState.done) for n in ("verify", "scores", "render")],
    )
    return RunConfig(
        run_id="r", docs_dir=tmp_path, bank_id="b", out_dir=tmp_path, workspace_dir=tmp_path
    )


async def test_rescue_appends_new_ids_updates_dropped_and_resets_stages(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path)

    rescued = await rescue_dropped(tmp_path, cfg, judge_provider())

    assert [(f.fact_id, f.source_entry_id) for f in rescued] == [("F002", "E2")]
    saved = read_models(tmp_path / "verified_facts.json", VerifiedFact)
    assert [f.fact_id for f in saved] == ["F001", "F002"]
    dropped = read_models(tmp_path / "dropped.json", DroppedEntry)
    assert [(d.entry.entry_id, d.stage) for d in dropped] == [
        ("E9", STAGE_CITATION),
        ("E3", STAGE_CITATION),
    ]
    states = {s.name: s.state for s in read_models(tmp_path / "stages.json", StageStatus)}
    assert states == {
        "verify": StageState.done,
        "scores": StageState.pending,
        "render": StageState.pending,
    }


async def test_rescue_with_nothing_rescued_leaves_stages_untouched(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path)

    rescued = await rescue_dropped(tmp_path, cfg, judge_provider(is_relevant=lambda i: False))

    assert rescued == []
    states = {s.name: s.state for s in read_models(tmp_path / "stages.json", StageStatus)}
    assert states["scores"] is StageState.done
    assert len(read_models(tmp_path / "verified_facts.json", VerifiedFact)) == 1


async def test_rescue_is_idempotent(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path)
    await rescue_dropped(tmp_path, cfg, judge_provider())
    again = await rescue_dropped(tmp_path, cfg, judge_provider())
    assert again == []
    assert len(read_models(tmp_path / "verified_facts.json", VerifiedFact)) == 2
