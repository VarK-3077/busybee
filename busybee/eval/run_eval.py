"""Evaluate a run: load its workspace, compute every metric, and write eval/<run_id>/ outputs.

`run_eval` primarily evaluates an EXISTING run workspace (`report.json`, `corpus/`,
`llm_log.jsonl`, `stages.json`); only when `run_pipeline=True` does it first lazily import
`busybee.orchestrate` and run the pipeline (expects `orchestrate.run_pipeline(RunConfig)`,
sync or async) to produce that workspace. `cli_eval` is the synchronous wrapper the CLI calls:
it builds the provider from the environment, runs `run_eval`, and returns the output directory
and markdown. Recall and precision are also reported for the main section, main + appendix and
all facts, filtered from the single set of judge calls using `out/data/shown_facts.json` (see
`metrics/shown_subsets.py`). LLM judge calls use tags `eval_match`, `eval_precision` and
`eval_citation` (temperature 0) and are audited to `<eval_root>/<run_id>/llm_log.jsonl`,
separate from the
run's own `llm_log.jsonl` so run statistics stay untouched. With `repeats` > 1 the three
LLM-judged metrics run that many times (the first repeat supplies the detailed result lists)
and metrics.md reports mean and min/max; deterministic metrics are computed once.
"""

import asyncio
import importlib
import inspect
from collections.abc import Mapping, Sequence
from pathlib import Path

from busybee.eval.gold import DEFAULT_GOLD_DIR, GoldSet, gold_path_for, load_gold
from busybee.eval.metrics.citation_precision import (
    CitationPrecisionResult,
    compute_citation_precision,
)
from busybee.eval.metrics.page_exact import compute_page_exact
from busybee.eval.metrics.planted_errors import compute_planted_error_catch
from busybee.eval.metrics.precision import PrecisionResult, compute_precision
from busybee.eval.metrics.proof_pass import compute_proof_pass
from busybee.eval.metrics.recall import RecallResult, compute_recall
from busybee.eval.metrics.run_stats import compute_run_stats
from busybee.eval.metrics.shown_subsets import (
    SHOWN_FACTS_RELATIVE,
    load_shown_sets,
    subset_scores,
)
from busybee.eval.report import (
    EvalMetrics,
    RepeatStat,
    metrics_markdown,
    repeat_stat,
    write_eval_report,
)
from busybee.index.embedder.protocol import Embedder
from busybee.index.store import VectorStore
from busybee.ingest.corpus_store import load_corpus
from busybee.llm import audit_log
from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk
from busybee.schema.facts import VerifiedFact
from busybee.schema.io import read_model, read_models
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Report
from busybee.schema.run import RunConfig
from busybee.verify.conflicts import is_conflicted
from busybee.verify.verify_entries import VerifyContext

DEFAULT_EVAL_ROOT = Path("eval")


async def _produce_workspace(
    company: str, bank_id: str, docs_dir: Path, workspace_dir: Path, out_dir: Path
) -> None:
    orchestrate = importlib.import_module("busybee.orchestrate")
    config = RunConfig(
        run_id=workspace_dir.name,
        docs_dir=docs_dir,
        bank_id=bank_id,
        out_dir=out_dir,
        workspace_dir=workspace_dir,
    )
    outcome = orchestrate.run_pipeline(config)
    if inspect.isawaitable(outcome):
        await outcome


def _load_gold(gold_path: str | Path | None, company: str, gold_dir: Path) -> GoldSet:
    return load_gold(gold_path if gold_path else gold_path_for(company, gold_dir))


def _scores(report: Report, workspace_dir: Path) -> list[ScoreResult]:
    path = workspace_dir / "scores.json"
    if report.scores or not path.exists():
        return report.scores
    return read_models(path, ScoreResult)


async def _judge_once(
    gold: GoldSet,
    facts: list[VerifiedFact],
    chunks_by_id: Mapping[str, Chunk],
    provider: Provider,
) -> tuple[RecallResult, PrecisionResult, CitationPrecisionResult]:
    return await asyncio.gather(
        compute_recall(gold.material_facts, facts, provider),
        compute_precision(facts, chunks_by_id, provider),
        compute_citation_precision(facts, chunks_by_id, provider),
    )


def _repeat_stats(
    judged: Sequence[tuple[RecallResult, PrecisionResult, CitationPrecisionResult]],
) -> dict[str, RepeatStat]:
    return {
        "recall": repeat_stat([r.recall for r, _, _ in judged]),
        "recall_must_have": repeat_stat([r.recall_must_have for r, _, _ in judged]),
        "precision": repeat_stat([p.precision for _, p, _ in judged]),
        "citation_precision": repeat_stat([c.citation_precision for _, _, c in judged]),
    }


async def run_eval(
    workspace_dir: str | Path,
    *,
    provider: Provider,
    company: str | None = None,
    bank_id: str | None = None,
    gold_path: str | Path | None = None,
    gold_dir: str | Path = DEFAULT_GOLD_DIR,
    eval_root: str | Path = DEFAULT_EVAL_ROOT,
    run_pipeline: bool = False,
    docs_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    store: VectorStore | None = None,
    embedder: Embedder | None = None,
    repeats: int = 1,
    shown_facts_path: str | Path | None = None,
) -> EvalMetrics:
    """Compute all metrics for the run in workspace_dir and write eval/<run_id>/ files."""
    workspace = Path(workspace_dir)
    if run_pipeline:
        if docs_dir is None or company is None or bank_id is None:
            raise ValueError("run_pipeline needs company, bank_id and docs_dir")
        await _produce_workspace(
            company, bank_id, Path(docs_dir), workspace, Path(out_dir or workspace)
        )
    report = read_model(workspace / "report.json", Report)
    company_name = company or report.company
    gold = _load_gold(gold_path, company_name, Path(gold_dir))
    corpus = load_corpus(workspace)
    every_fact = list(report.facts.values())
    facts = [fact for fact in every_fact if not is_conflicted(fact)]
    ctx = VerifyContext(
        provider=provider,
        chunks_by_id=corpus.chunks_by_id,
        store=store,
        embedder=embedder,
    )
    repeats = max(1, repeats)
    audit_log.configure(Path(eval_root) / report.run_id / "llm_log.jsonl")
    try:
        judged, planted = await asyncio.gather(
            asyncio.gather(
                *(_judge_once(gold, facts, corpus.chunks_by_id, provider) for _ in range(repeats))
            ),
            compute_planted_error_catch(gold.planted_errors, ctx, every_fact),
        )
    finally:
        audit_log.configure(None)
    recall, precision, citation = judged[0]
    shown = load_shown_sets(
        shown_facts_path if shown_facts_path else workspace / SHOWN_FACTS_RELATIVE
    )
    metrics = EvalMetrics(
        run_id=report.run_id,
        company=company_name,
        bank_id=bank_id or report.bank_id,
        num_facts=len(facts),
        recall=recall,
        precision=precision,
        citation=citation,
        page_exact=compute_page_exact(facts, corpus.chunks_by_id),
        planted=planted,
        proof=compute_proof_pass(_scores(report, workspace), report.inferences),
        stats=compute_run_stats(workspace),
        subsets=subset_scores(
            shown, gold.material_facts, recall, precision, [f.fact_id for f in facts]
        ),
        repeats=repeats,
        repeat_stats=_repeat_stats(judged) if repeats > 1 else {},
    )
    write_eval_report(metrics, eval_root)
    return metrics


def cli_eval(
    workspace_dir: str | Path,
    *,
    company: str | None = None,
    bank_id: str | None = None,
    gold_path: str | Path | None = None,
    eval_root: str | Path = DEFAULT_EVAL_ROOT,
    run_pipeline: bool = False,
    docs_dir: str | Path | None = None,
    provider: Provider | None = None,
    repeats: int = 1,
) -> tuple[Path, str]:
    """Synchronous entry for the CLI: evaluate a run; return (output dir, markdown table)."""
    from busybee.llm import provider_from_env

    judge = provider or provider_from_env("eval")
    metrics = asyncio.run(
        run_eval(
            workspace_dir,
            provider=judge,
            company=company,
            bank_id=bank_id,
            gold_path=gold_path,
            eval_root=eval_root,
            run_pipeline=run_pipeline,
            docs_dir=docs_dir,
            repeats=repeats,
        )
    )
    return Path(eval_root) / metrics.run_id, metrics_markdown(metrics)
