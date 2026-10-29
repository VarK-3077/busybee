"""Adversary stage with a scripted provider: answered, unanswered, rejected, and the draft."""

import json
from pathlib import Path

import numpy as np

from busybee.adversary import draft_markdown, run_adversary
from busybee.index import HashingEmbedder, VectorStore
from busybee.ingest.corpus_store import write_corpus
from busybee.llm import Message, MockProvider
from busybee.schema.documents import Chunk, Document, DocumentKind, Page
from busybee.schema.facts import FactCategory, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.policy import BoundInput, ScoreResult
from busybee.schema.report import Concern, Inference
from busybee.schema.run import RunConfig

TEXT = "The company has no pending litigation as of March 2024."
CHUNK = Chunk(chunk_id="D1:p1:c0", doc_id="D1", page_no=1, index_in_page=0, text=TEXT)
FACT = VerifiedFact(
    fact_id="F001", statement="Revenue was Rs 10 crore", category=FactCategory.revenue
)


def _provider(
    questions: list[dict], *, reject: bool = False, answered: bool = True
) -> MockProvider:
    def respond(messages: list[Message], task: str) -> str:
        if task == "adversary_questions":
            return json.dumps({"items": questions})
        if task == "adversary_answer":
            if not answered:
                return json.dumps({"answered": False})
            return json.dumps(
                {
                    "answered": True,
                    "statement": "The company has no pending litigation",
                    "category": "litigation_regulatory",
                }
            )
        if reject:
            return json.dumps({"verdict": "unsupported"})
        return json.dumps({"verdict": "supported", "quote": TEXT, "note": "ok"})

    return MockProvider(respond)


async def _workspace(tmp_path: Path) -> RunConfig:
    document = Document(
        doc_id="D1",
        title="AR",
        kind=DocumentKind.annual_report,
        source_path="x",
        sha256="0",
        num_pages=1,
    )
    write_corpus(tmp_path, [document], {"D1": [Page(doc_id="D1", page_no=1, text=TEXT)]}, [CHUNK])
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add([CHUNK], await embedder.embed([TEXT]))
    store.save(tmp_path / "index")
    write_models_atomic(tmp_path / "verified_facts.json", [FACT])
    return RunConfig(
        run_id="r", docs_dir=tmp_path, bank_id="b", out_dir=tmp_path, workspace_dir=tmp_path
    )


QUESTION = {
    "question": "Is there pending litigation?",
    "why": "litigation risk",
    "related_fact_ids": ["F001", "F999"],
    "search_query": "pending litigation",
}


async def test_answered_question_appends_fact(tmp_path: Path) -> None:
    cfg = await _workspace(tmp_path)
    concerns = await run_adversary(tmp_path, cfg, _provider([QUESTION]))
    facts = read_models(tmp_path / "verified_facts.json", VerifiedFact)
    assert [f.fact_id for f in facts] == ["F001", "F002"]
    assert facts[1].added_by == "adversary"
    assert facts[1].citations[0].chunk_id == "D1:p1:c0"
    assert [(c.found, c.fact_ids) for c in concerns] == [(True, ["F002"])]


async def test_unanswered_question_becomes_concern(tmp_path: Path) -> None:
    cfg = await _workspace(tmp_path)
    await run_adversary(tmp_path, cfg, _provider([QUESTION], answered=False))
    saved = read_models(tmp_path / "concerns.json", Concern)
    assert len(read_models(tmp_path / "verified_facts.json", VerifiedFact)) == 1
    assert saved[0].found is False
    assert saved[0].concern_id == "C001"
    assert saved[0].fact_ids == ["F001"]
    assert saved[0].query_used == "pending litigation"
    assert "litigation risk" in saved[0].reasoning


async def test_entailment_rejection_becomes_concern(tmp_path: Path) -> None:
    cfg = await _workspace(tmp_path)
    concerns = await run_adversary(tmp_path, cfg, _provider([QUESTION], reject=True))
    assert concerns[0].found is False
    assert "entailment" in concerns[0].reasoning


def test_draft_markdown_has_every_section() -> None:
    score = ScoreResult(
        score_id="S1",
        value_display="3.1x",
        grade="B",
        inputs=[BoundInput(slot="a", fact_id="F001", value=1)],
    )
    inference = Inference(inference_id="I001", opinion="Healthy", fact_ids=["F001"])
    text = draft_markdown([FACT], [score], [inference])
    for part in (
        "## Facts",
        "### revenue",
        "F001: Revenue",
        "## Scores",
        "S1: 3.1x",
        "## Inferences",
        "I001: Healthy",
    ):
        assert part in text
    assert "(none)" in draft_markdown([], [], [])


async def test_rerun_does_not_duplicate_adversary_facts(tmp_path: Path) -> None:
    cfg = await _workspace(tmp_path)
    await run_adversary(tmp_path, cfg, _provider([QUESTION]))
    concerns = await run_adversary(tmp_path, cfg, _provider([QUESTION]))
    facts = read_models(tmp_path / "verified_facts.json", VerifiedFact)
    assert [(f.fact_id, f.added_by) for f in facts] == [("F001", None), ("F002", "adversary")]
    assert [(c.found, c.fact_ids) for c in concerns] == [(True, ["F002"])]


def _q(n: int, severity: str, related: list[str]) -> dict:
    return {
        "question": f"Question {n}?",
        "why": "w",
        "severity": severity,
        "related_fact_ids": related,
        "search_query": f"query {n}",
    }


async def test_open_concerns_capped_at_five_by_severity_and_related_facts(tmp_path: Path) -> None:
    cfg = await _workspace(tmp_path)
    questions = [
        _q(1, "low", ["F001"]),
        _q(2, "medium", []),
        _q(3, "high", ["F001"]),
        _q(4, "high", []),
        _q(5, "medium", ["F001"]),
        _q(6, "low", []),
        _q(7, "medium", ["F001", "F001"]),
        _q(8, "low", ["F001"]),
    ]
    concerns = await run_adversary(tmp_path, cfg, _provider(questions, answered=False))

    assert [c.opinion for c in concerns] == [
        "Question 3?",
        "Question 7?",
        "Question 5?",
        "Question 2?",
        "Question 4?",
    ]
    assert [c.severity for c in concerns] == ["high", "medium", "medium", "medium", "medium"]
    saved = read_models(tmp_path / "concerns.json", Concern)
    cut = read_models(tmp_path / "concerns_dropped.json", Concern)
    assert len(saved) == 5
    assert sorted(c.opinion for c in cut) == ["Question 1?", "Question 6?", "Question 8?"]
    assert all("top 5" in c.dropped_reason for c in cut)


async def test_high_severity_without_related_facts_is_lowered(tmp_path: Path) -> None:
    cfg = await _workspace(tmp_path)
    concerns = await run_adversary(
        tmp_path, cfg, _provider([_q(1, "high", ["F999"])], answered=False)
    )
    assert concerns[0].severity == "medium"
