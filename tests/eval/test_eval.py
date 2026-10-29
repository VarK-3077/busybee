"""Eval metrics on tiny hand-made inputs with scripted mock judges."""

import json
import re
from pathlib import Path

import pytest

from busybee.eval.gold import GoldFact, PlantedError, gold_path_for, load_gold
from busybee.eval.judge import candidate_facts, match_statements
from busybee.eval.metrics.citation_precision import compute_citation_precision
from busybee.eval.metrics.page_exact import compute_page_exact
from busybee.eval.metrics.planted_errors import (
    best_matching_chunk,
    compute_planted_error_catch,
    planted_entries,
)
from busybee.eval.metrics.precision import compute_precision
from busybee.eval.metrics.proof_pass import compute_proof_pass
from busybee.eval.metrics.recall import compute_recall
from busybee.eval.metrics.run_stats import compute_run_stats
from busybee.eval.report import metrics_markdown
from busybee.eval.run_eval import run_eval
from busybee.ingest.corpus_store import write_corpus
from busybee.llm import Message, MockProvider, StructuredOutputError
from busybee.llm.audit_log import AuditEntry
from busybee.schema.documents import Chunk, Document, Page
from busybee.schema.facts import Citation, Verification, VerificationStatus, VerifiedFact
from busybee.schema.io import append_jsonl, write_json_atomic, write_model_atomic
from busybee.schema.lean import CompileResult, LeanArtifact, LeanArtifactKind
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Inference, Report
from busybee.verify.verify_entries import VerifyContext

CHUNKS = [
    Chunk(
        chunk_id="D1:p1:c0",
        doc_id="D1",
        page_no=1,
        index_in_page=0,
        text="Revenue for FY25 was Rs 931.2 crore, up from Rs 845.5 crore in FY24.",
    ),
    Chunk(
        chunk_id="D1:p2:c0",
        doc_id="D1",
        page_no=2,
        index_in_page=0,
        text="Total borrowings were Rs 300 crore at 31 March 2025.",
    ),
]


def fact(fact_id: str, statement: str, chunk: Chunk, quote: str) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        citations=[
            Citation(
                chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no, quote=quote
            )
        ],
    )


FACTS = [
    fact("F1", "Revenue was Rs 931.2 crore in FY25.", CHUNKS[0], "Revenue for FY25 was Rs 931.2"),
    fact("F2", "Borrowings were Rs 300 crore.", CHUNKS[1], "made up quote"),
]


def judge(messages: list[Message], task: str) -> str:
    text = messages[-1].content
    if task == "eval_match":
        golds = re.findall(r"^GOLD (\S+):", text, re.MULTILINE)
        out = [{"gold_id": g, "fact_ids": ["F1"] if "F1" in text else []} for g in golds]
        return json.dumps({"matches": out})
    ids = re.findall(r"^FACT (\S+):", text, re.MULTILINE)
    if task == "eval_precision":
        return json.dumps(
            {"verdicts": [{"fact_id": i, "important": True, "correct": i == "F1"} for i in ids]}
        )
    if task == "eval_citation":
        return json.dumps({"verdicts": [{"fact_id": i, "supported": i == "F1"} for i in ids]})
    if task == "verify_entailment":
        return json.dumps({"verdict": "unsupported", "quote": "", "note": "no"})
    return "{}"


def test_gold_loading_and_paths(tmp_path: Path) -> None:
    assert gold_path_for("Acme Textiles Limited").name == "acme_textiles.json"
    path = tmp_path / "g.json"
    write_json_atomic(
        path,
        {
            "company": "A",
            "material_facts": [{"statement": "x 1"}],
            "planted_errors": [{"statement": "y 2", "why_wrong": "z"}],
        },
    )
    gold = load_gold(path)
    assert gold.material_facts[0].must_have and gold.planted_errors[0].why_wrong == "z"


async def test_prefilter_and_match() -> None:
    assert [f.fact_id for f in candidate_facts("Revenue 931.2 crore", FACTS)] == ["F1"]
    provider = MockProvider(judge)
    result = await match_statements(["Revenue was 931.2 crore", "No numbers here"], FACTS, provider)
    assert result == {0: ["F1"], 1: []}
    assert len(provider.calls) == 1


async def test_recall() -> None:
    golds = [
        GoldFact(statement="Revenue FY25 Rs 931.2 crore F1"),
        GoldFact(statement="EBITDA 130.4 crore", must_have=False),
    ]
    result = await compute_recall(golds, FACTS, MockProvider(judge))
    assert result.recall == 0.5 and result.recall_must_have == 1.0
    assert result.missed == ["EBITDA 130.4 crore"]


async def test_precision_and_citation_precision() -> None:
    provider = MockProvider(judge)
    by_id = {c.chunk_id: c for c in CHUNKS}
    precision = await compute_precision(FACTS, by_id, provider)
    assert precision.precision == 0.5 and precision.incorrect == ["F2"]
    citation = await compute_citation_precision(FACTS, by_id, provider)
    assert citation.citation_precision == 0.5 and citation.unsupported == ["F2"]


def test_page_exact() -> None:
    result = compute_page_exact(FACTS, {c.chunk_id: c for c in CHUNKS})
    assert result.page_exact == 0.5 and result.failures == ["F2 -> D1:p2:c0"]


def test_planted_injection_shape() -> None:
    errors = [PlantedError(statement="Revenue was Rs 931.2 crore in FY25 and 999 crore")]
    assert best_matching_chunk(errors[0].statement, CHUNKS) is CHUNKS[0]
    (entry,) = planted_entries(errors, CHUNKS)
    assert entry.entry_id == "PLANTED001"
    assert entry.citations[0].chunk_id == "D1:p1:c0"


async def test_planted_error_catch_rate() -> None:
    errors = [
        PlantedError(statement="Total borrowings were Rs 3,000 crore"),
        PlantedError(statement="Total borrowings were Rs 300 crore at 31 March 2025."),
    ]
    ctx = VerifyContext(
        provider=MockProvider(judge),
        chunks_by_id={c.chunk_id: c for c in CHUNKS},
        store=None,
        embedder=None,
    )
    result = await compute_planted_error_catch(errors, ctx)
    assert result.caught == 1 and result.catch_rate == 0.5
    assert result.missed == [errors[1].statement]
    assert (result.dropped_by_verify, result.absent_from_report) == (1, 0)


async def test_planted_error_absent_from_report_counts_as_caught() -> None:
    errors = [
        PlantedError(statement="Total borrowings were Rs 3,000 crore"),
        PlantedError(statement="Total borrowings were Rs 300 crore at 31 March 2025."),
    ]
    ctx = VerifyContext(
        provider=MockProvider(judge),
        chunks_by_id={c.chunk_id: c for c in CHUNKS},
        store=None,
        embedder=None,
    )
    only_revenue = [FACTS[0]]
    result = await compute_planted_error_catch(errors, ctx, only_revenue)
    assert (result.dropped_by_verify, result.absent_from_report) == (1, 1)
    assert result.caught == 2 and result.total == 2 and result.catch_rate == 1.0
    assert result.missed == []

    both = await compute_planted_error_catch(errors, ctx, FACTS)
    assert both.absent_from_report == 0
    assert both.missed == [errors[1].statement] and both.catch_rate == 0.5


async def test_planted_error_present_only_as_conflicted_fact_counts_as_caught() -> None:
    errors = [PlantedError(statement="Total borrowings were Rs 300 crore at 31 March 2025.")]
    ctx = VerifyContext(
        provider=MockProvider(judge),
        chunks_by_id={c.chunk_id: c for c in CHUNKS},
        store=None,
        embedder=None,
    )
    live = await compute_planted_error_catch(errors, ctx, FACTS)
    assert live.caught == 0 and live.missed == [errors[0].statement]

    demoted = [
        f.model_copy(update={"verification": Verification(status=VerificationStatus.conflicted)})
        for f in FACTS
    ]
    result = await compute_planted_error_catch(errors, ctx, demoted)
    assert (result.caught, result.absent_from_report, result.conflicted) == (1, 1, 1)
    assert result.missed == []


def artifact(artifact_id: str, ok: bool | None) -> LeanArtifact:
    compile_result = None if ok is None else CompileResult(ok=ok)
    return LeanArtifact(
        artifact_id=artifact_id, kind=LeanArtifactKind.scores, compile=compile_result
    )


def test_proof_pass() -> None:
    scores = [
        ScoreResult(score_id="S1", status="computed", lean=artifact("a", True)),
        ScoreResult(score_id="S2", status="not_computable"),
    ]
    inferences = [
        Inference(inference_id="I1", opinion="o", lean=artifact("b", False)),
        Inference(inference_id="I2", opinion="o", lean=artifact("c", None)),
    ]
    result = compute_proof_pass(scores, inferences)
    assert result.proof_pass == 1 / 3 and result.failed == ["b", "c"]
    assert compute_proof_pass([], []).proof_pass is None


def test_run_stats(tmp_path: Path) -> None:
    write_json_atomic(
        tmp_path / "stages.json",
        [
            {
                "name": "ingest",
                "state": "done",
                "started_at": "2026-01-01T00:00:00",
                "finished_at": "2026-01-01T00:00:05",
            },
            {"name": "extract", "state": "pending"},
        ],
    )
    for task in ("a", "a", "b"):
        append_jsonl(tmp_path / "llm_log.jsonl", AuditEntry(task=task))
    stats = compute_run_stats(tmp_path)
    assert stats.stage_seconds == {"ingest": 5.0} and stats.total_seconds == 5.0
    assert stats.calls_per_task == {"a": 2, "b": 1} and stats.total_calls == 3


async def test_run_eval_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "ws" / "r1"
    docs = [Document(doc_id="D1", title="AR")]
    pages = {
        "D1": [
            Page(doc_id="D1", page_no=1, text=CHUNKS[0].text),
            Page(doc_id="D1", page_no=2, text=CHUNKS[1].text),
        ]
    }
    write_corpus(workspace, docs, pages, CHUNKS)
    report = Report(
        run_id="r1", company="Acme Textiles Limited", facts={f.fact_id: f for f in FACTS}
    )
    write_model_atomic(workspace / "report.json", report)
    gold = tmp_path / "gold.json"
    write_json_atomic(
        gold,
        {
            "material_facts": [{"statement": "Revenue 931.2 crore F1"}],
            "planted_errors": [{"statement": "Borrowings were Rs 3,000 crore"}],
        },
    )
    metrics = await run_eval(
        workspace, provider=MockProvider(judge), gold_path=gold, eval_root=tmp_path / "eval"
    )
    assert metrics.recall.recall == 1.0 and metrics.planted.catch_rate == 1.0
    saved = json.loads((tmp_path / "eval" / "r1" / "metrics.json").read_text())
    assert saved["num_facts"] == 2
    assert "| Page-exact rate | 50.0% |" in (tmp_path / "eval" / "r1" / "metrics.md").read_text()
    assert "n/a" in metrics_markdown(metrics)


async def test_run_eval_subsets_filter_one_set_of_judge_calls(tmp_path: Path) -> None:
    workspace = tmp_path / "ws" / "r1"
    write_corpus(
        workspace,
        [Document(doc_id="D1", title="AR")],
        {"D1": [Page(doc_id="D1", page_no=1, text=CHUNKS[0].text)]},
        CHUNKS,
    )
    write_model_atomic(
        workspace / "report.json",
        Report(run_id="r1", company="Acme", facts={f.fact_id: f for f in FACTS}),
    )
    write_json_atomic(
        workspace / "out" / "data" / "shown_facts.json", {"main": ["F2"], "appendix": ["F1"]}
    )
    gold = tmp_path / "gold.json"
    write_json_atomic(gold, {"material_facts": [{"statement": "Revenue 931.2 crore F1"}]})
    provider = MockProvider(judge)
    metrics = await run_eval(
        workspace, provider=provider, gold_path=gold, eval_root=tmp_path / "eval"
    )
    by_name = {s.name: s for s in metrics.subsets}
    assert (by_name["main"].recall, by_name["main"].precision) == (0.0, 0.0)
    assert (by_name["main + appendix"].recall, by_name["main + appendix"].precision) == (1.0, 0.5)
    assert by_name["all facts"].num_facts == 2 and by_name["all facts"].recall == 1.0
    assert (
        "| main + appendix | 2 | 100.0% | 100.0% | 50.0% |"
        in (tmp_path / "eval" / "r1" / "metrics.md").read_text()
    )


def test_cli_eval_prints_metrics_table(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from busybee.cli import app

    workspace = tmp_path / "ws" / "r1"
    write_corpus(
        workspace,
        [Document(doc_id="D1", title="AR")],
        {"D1": [Page(doc_id="D1", page_no=1, text=CHUNKS[0].text)]},
        CHUNKS[:1],
    )
    report = Report(run_id="r1", company="Acme", facts={f.fact_id: f for f in FACTS[:1]})
    write_model_atomic(workspace / "report.json", report)
    gold = tmp_path / "gold.json"
    write_json_atomic(gold, {"material_facts": [{"statement": "Revenue 931.2 crore F1"}]})
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "mock")
    monkeypatch.setattr("busybee.llm.registry.provider_from_env", lambda _task: MockProvider(judge))
    monkeypatch.setattr("busybee.llm.provider_from_env", lambda _task: MockProvider(judge))

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--workspace-dir",
            str(workspace),
            "--gold",
            str(gold),
            "--eval-root",
            str(tmp_path / "eval"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Page-exact rate" in result.output
    assert (tmp_path / "eval" / "r1" / "metrics.md").exists()


async def test_match_accepts_gold_id_echoed_with_the_block_header() -> None:
    reply = '{"matches": [{"gold_id": "GOLD 0", "fact_ids": ["F1"]}]}'
    provider = MockProvider({"eval_match": [reply]})
    result = await match_statements(["Revenue was 931.2 crore"], FACTS, provider)
    assert result == {0: ["F1"]}


async def test_gold_fact_covered_by_union_of_facts() -> None:
    facts = [
        fact("F1", "Revenue was Rs 931.2 crore.", CHUNKS[0], "q"),
        fact("F2", "Revenue grew from Rs 845.5 crore.", CHUNKS[0], "q"),
    ]
    gold = "Revenue rose from 845.5 crore to 931.2 crore"
    reply = '{"matches": [{"gold_id": "0", "fact_ids": ["F1", "F2"]}]}'
    assert await match_statements([gold], facts, MockProvider({"eval_match": [reply]})) == {
        0: ["F1", "F2"]
    }
    invalid = '{"matches": [{"gold_id": "0", "fact_ids": ["F1", "F9"]}]}'
    assert await match_statements([gold], facts, MockProvider({"eval_match": [invalid]})) == {0: []}
    legacy = '{"matches": [{"gold_id": "0", "fact_id": "F2"}]}'
    assert await match_statements([gold], facts, MockProvider({"eval_match": [legacy]})) == {
        0: ["F2"]
    }
    result = await compute_recall(
        [GoldFact(statement=gold)], facts, MockProvider({"eval_match": [reply]})
    )
    assert result.matched_fact_ids == {gold: ["F1", "F2"]} and result.matches == {gold: "F1"}


def test_candidates_ignore_years_and_common_numbers() -> None:
    facts = [
        VerifiedFact(fact_id=f"F{i}", statement=f"Item {i} was reported in FY25 for 2025 amount")
        for i in range(30)
    ]
    facts.append(VerifiedFact(fact_id="T", statement="Revenue in FY25 was Rs 931.2 crore"))
    assert [f.fact_id for f in candidate_facts("Revenue FY25 931.2 crore", facts)] == ["T"]
    assert candidate_facts("Reported FY25 2025", facts) == []
    many = [
        VerifiedFact(fact_id=f"G{i}", statement=f"Debt of 777 crore note {i}") for i in range(30)
    ]
    many.append(VerifiedFact(fact_id="U", statement="Debt of 777 crore and 55.5 crore leverage"))
    assert [f.fact_id for f in candidate_facts("Leverage 55.5 crore, debt 777 crore", many)] == [
        "U"
    ]
    assert (
        len(
            candidate_facts(
                "Leverage of 12.5 crore",
                [VerifiedFact(fact_id=f"H{i}", statement="Leverage 12.5 crore") for i in range(12)],
            )
        )
        == 8
    )


async def test_eval_calls_are_audited_and_repeats_summarised(tmp_path: Path) -> None:
    workspace = tmp_path / "ws" / "r1"
    write_corpus(
        workspace,
        [Document(doc_id="D1", title="AR")],
        {"D1": [Page(doc_id="D1", page_no=1, text=CHUNKS[0].text)]},
        CHUNKS[:1],
    )
    write_model_atomic(
        workspace / "report.json",
        Report(run_id="r1", company="Acme", facts={f.fact_id: f for f in FACTS[:1]}),
    )
    gold = tmp_path / "gold.json"
    write_json_atomic(gold, {"material_facts": [{"statement": "Revenue 931.2 crore F1"}]})
    provider = MockProvider(judge)
    metrics = await run_eval(
        workspace, provider=provider, gold_path=gold, eval_root=tmp_path / "eval", repeats=3
    )
    assert metrics.repeats == 3 and metrics.repeat_stats["recall"].values == [1.0, 1.0, 1.0]
    assert {c.temperature for c in provider.calls} == {0.0}
    log = (tmp_path / "eval" / "r1" / "llm_log.jsonl").read_text().splitlines()
    tasks = [json.loads(line)["task"] for line in log]
    assert tasks.count("eval_match") == 3 and tasks.count("eval_precision") == 3
    assert tasks.count("eval_citation") == 3
    assert (
        "mean (min 100.0%, max 100.0%, n=3)"
        in (tmp_path / "eval" / "r1" / "metrics.md").read_text()
    )


def test_page_exact_accepts_a_quote_from_the_table_header_prefix() -> None:
    chunk = Chunk(
        chunk_id="D1:p4:c1",
        doc_id="D1",
        page_no=4,
        index_in_page=1,
        text="Total Assets | 2,36,510.84",
        prefix="[TABLE: Note | March 31, 2026]",
    )
    fact = VerifiedFact(
        fact_id="F1",
        statement="s",
        citations=[
            Citation(chunk_id="D1:p4:c1", doc_id="D1", page_no=4, quote="March 31, 2026]"),
            Citation(chunk_id="D1:p4:c1", doc_id="D1", page_no=4, quote="Total Assets"),
            Citation(chunk_id="D1:p4:c1", doc_id="D1", page_no=4, quote=""),
        ],
    )
    result = compute_page_exact([fact], {chunk.chunk_id: chunk})
    assert (result.exact, result.total) == (2, 3)


def test_page_exact_ignores_bank_supplied_figures() -> None:
    fact = VerifiedFact(
        fact_id="F1",
        statement="Bank input: proposed exposure INR 150 crore",
        citations=[
            Citation(chunk_id="REQ:p1:c1", doc_id="REQ", page_no=1, quote="x", source="bank_input")
        ],
    )
    result = compute_page_exact([fact], {})
    assert result.total == 0 and result.failures == []


def test_candidates_compare_amounts_in_canonical_crore() -> None:
    lakh = VerifiedFact(fact_id="L", statement="Net worth stood at Rs 9,868.39 lakhs")
    other = VerifiedFact(fact_id="O", statement="Net worth stood at Rs 98.0 crore")
    found = candidate_facts("Net worth was 98.67 crore", [other, lakh])
    assert [f.fact_id for f in found] == ["L"]


def _truncating_judge(limit: int):
    def reply(messages: list[Message], task: str) -> str:
        text = messages[-1].content
        size = len(re.findall(r"^(?:GOLD|FACT) ", text, re.MULTILINE))
        if size > limit:
            raise StructuredOutputError("reply truncated", truncated=True)
        return judge(messages, task)

    return reply


def _many_facts(count: int) -> list[VerifiedFact]:
    return [fact(f"F{i}", f"Revenue was Rs 931.{i} crore.", CHUNKS[0], "q") for i in range(count)]


async def test_match_halves_truncated_batches() -> None:
    facts = _many_facts(4)
    statements = [f"Revenue was 931.{i} crore F1" for i in range(4)]
    provider = MockProvider(_truncating_judge(1))
    result = await match_statements(statements, facts, provider, batch_size=4)
    assert result == {i: ["F1"] for i in range(4)} and len(provider.calls) == 7


async def test_match_single_truncating_item_is_unmatched(caplog) -> None:
    provider = MockProvider(_truncating_judge(0))
    result = await match_statements(["Revenue was 931.1 crore"], _many_facts(3), provider)
    assert result == {0: []} and "truncated" in caplog.text


async def test_precision_and_citation_halve_truncated_batches() -> None:
    facts = _many_facts(5)
    by_id = {c.chunk_id: c for c in CHUNKS}
    provider = MockProvider(_truncating_judge(2))
    precision = await compute_precision(facts, by_id, provider, batch_size=5)
    assert precision.total == 5 and precision.good == 1 and len(precision.incorrect) == 4
    citation = await compute_citation_precision(facts, by_id, provider, batch_size=5)
    assert citation.supported == 1 and citation.total == 5
    lone = MockProvider(_truncating_judge(0))
    assert (await compute_citation_precision(facts[:1], by_id, lone)).unsupported == ["F0"]


async def test_non_truncation_errors_still_raise() -> None:
    def broken(messages: list[Message], task: str) -> str:
        raise StructuredOutputError("bad json")

    with pytest.raises(StructuredOutputError):
        await match_statements(["Revenue was 931.1 crore"], _many_facts(2), MockProvider(broken))
