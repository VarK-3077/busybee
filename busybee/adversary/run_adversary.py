"""Run the adversary stage over a workspace.

Reads `verified_facts.json`, optional `scores.json` and `inferences.json`, builds the markdown
draft, asks the fresh-context critic for questions, and tries to answer each concurrently from
the vector index. Answers become `added_by="adversary"` notebook entries that go through
`verify_entries` (without the relevance pass); survivors are numbered after the existing facts
and appended to `verified_facts.json`. The stage is idempotent: facts a previous run added
(`added_by="adversary"`) are dropped first and regenerated. Every question yields one concern in
`concerns.json`:
`found=True` pointing at the new fact id, or `found=False` with the question's `why` as
reasoning (also when the answer was found but failed verification). Each concern carries the
critic's severity. Only the `MAX_OPEN_CONCERNS` most important open concerns (severity, then
number of related facts) stay in `concerns.json`; the rest are written to
`concerns_dropped.json` with a `dropped_reason`, so nothing is lost. Dropped entries are
appended to `dropped.json`. New facts are also checked against the existing ones for cross-document
conflicts (`busybee.verify.detect_and_resolve_conflicts`); conflict concerns are appended to
`conflicts.json`, which verify wrote, and facts left `conflicted` stay out of the critic's draft.
The index is loaded from `<workspace>/index`; without one every
question stays an open concern.
"""

import asyncio
from pathlib import Path

from busybee.extract.condensed import condense_notebook
from busybee.index import VectorStore, embedder_from_env
from busybee.ingest.corpus_store import load_corpus
from busybee.llm.provider import Provider
from busybee.schema.facts import DroppedEntry, NotebookEntry, VerifiedFact
from busybee.schema.ids import make_concern_id
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Concern, Inference
from busybee.schema.run import RunConfig
from busybee.verify import (
    VerifyContext,
    assign_fact_ids,
    detect_and_resolve_conflicts,
    is_conflicted,
    undo_conflicts_involving,
    verify_entries,
)
from busybee.verify.conflicts import next_conflict_number
from busybee.verify.run_verify import CONFLICTS_FILE

from .draft_markdown import draft_markdown
from .questions import Question, ask_questions, rank_key
from .search_gaps import GapResult, answer_question


def _read_optional[ModelT](path: Path, model: type[ModelT]) -> list[ModelT]:
    return read_models(path, model) if path.is_file() else []  # type: ignore[type-var]


MAX_OPEN_CONCERNS = 5
DROPPED_CONCERNS_FILE = "concerns_dropped.json"


def split_open_concerns(
    concerns: list[Concern], questions: list[Question]
) -> tuple[list[Concern], list[Concern]]:
    """Keep answered concerns plus the top MAX_OPEN_CONCERNS open ones; return (kept, dropped)."""
    by_id = {c.concern_id: q for c, q in zip(concerns, questions, strict=True)}
    open_ranked = sorted(
        (c for c in concerns if not c.found),
        key=lambda c: (*rank_key(by_id[c.concern_id]), c.concern_id),
    )
    cut = {c.concern_id for c in open_ranked[MAX_OPEN_CONCERNS:]}
    kept = [c for c in concerns if c.found] + open_ranked[:MAX_OPEN_CONCERNS]
    dropped = [
        c.model_copy(
            update={
                "dropped_reason": (
                    f"ranked below the top {MAX_OPEN_CONCERNS} open concerns "
                    f"(severity {c.severity})"
                )
            }
        )
        for c in concerns
        if c.concern_id in cut
    ]
    return kept, dropped


def _entry_id(position: int) -> str:
    return f"ADV:E{position:03d}"


def _concern(
    position: int, question: Question, *, found: bool, reason: str, fact_ids: list[str]
) -> Concern:
    reasoning = question.why or question.question
    if reason:
        reasoning = f"{reasoning} ({reason})"
    return Concern(
        concern_id=make_concern_id(position),
        opinion=question.question,
        fact_ids=fact_ids,
        reasoning=reasoning,
        query_used=question.search_query,
        found=found,
        severity=question.severity,
    )


def _merge_dropped(existing: list[DroppedEntry], new: list[DroppedEntry]) -> list[DroppedEntry]:
    seen = {(item.entry.entry_id, item.stage) for item in existing}
    return [*existing, *(item for item in new if (item.entry.entry_id, item.stage) not in seen)]


async def _answer_all(
    questions: list[Question], workspace: Path, provider: Provider
) -> list[GapResult]:
    index_dir = workspace / "index"
    if not (index_dir / "vectors.npy").exists():
        return [GapResult(None, "no document index available") for _ in questions]
    store = VectorStore.load(index_dir)
    embedder = embedder_from_env()
    return list(
        await asyncio.gather(
            *(
                answer_question(
                    question,
                    _entry_id(position),
                    store=store,
                    embedder=embedder,
                    provider=provider,
                )
                for position, question in enumerate(questions, start=1)
            )
        )
    )


async def run_adversary(
    workspace_dir: str | Path, cfg: RunConfig, provider: Provider
) -> list[Concern]:
    """Critique the draft, append verified answers as facts, write concerns.json."""
    workspace = Path(workspace_dir)
    all_facts = read_models(workspace / "verified_facts.json", VerifiedFact)
    base_facts = [fact for fact in all_facts if fact.added_by != "adversary"]
    removed_ids = {fact.fact_id for fact in all_facts if fact.added_by == "adversary"}
    base_facts, prior_conflicts = undo_conflicts_involving(
        base_facts, _read_optional(workspace / CONFLICTS_FILE, Concern), removed_ids
    )
    facts = [fact for fact in base_facts if not is_conflicted(fact)]
    scores = _read_optional(workspace / "scores.json", ScoreResult)
    inferences = _read_optional(workspace / "inferences.json", Inference)
    draft = draft_markdown(facts, scores, inferences)
    questions = await ask_questions(draft, provider, {fact.fact_id for fact in facts})
    results = await _answer_all(questions, workspace, provider)

    entries = [result.entry for result in results if result.entry is not None]
    store_dir = workspace / "index"
    corpus = load_corpus(workspace)
    ctx = VerifyContext(
        provider=provider,
        chunks_by_id=corpus.chunks_by_id,
        store=VectorStore.load(store_dir) if (store_dir / "vectors.npy").exists() else None,
        embedder=embedder_from_env() if (store_dir / "vectors.npy").exists() else None,
        notebook_context=condense_notebook(_as_entries(facts)),
    )
    verified, dropped = await verify_entries(entries, ctx, check_relevance=False)
    start = _next_number(base_facts)
    numbered = assign_fact_ids(verified, start=start)
    by_entry = {fact.source_entry_id: fact.fact_id for fact in numbered}

    concerns: list[Concern] = []
    for position, (question, result) in enumerate(zip(questions, results, strict=True), start=1):
        entry = result.entry
        new_id = by_entry.get(entry.entry_id) if entry is not None else None
        if new_id is not None:
            concerns.append(_concern(position, question, found=True, reason="", fact_ids=[new_id]))
            continue
        reason = result.reason or "answer failed citation verification"
        concerns.append(
            _concern(
                position, question, found=False, reason=reason, fact_ids=question.related_fact_ids
            )
        )

    dropped_path = workspace / "dropped.json"
    existing = read_models(dropped_path, DroppedEntry) if dropped_path.is_file() else []
    outcome = await detect_and_resolve_conflicts(
        [*base_facts, *numbered],
        corpus.documents,
        provider,
        only_involving={fact.fact_id for fact in numbered},
        start_number=next_conflict_number(prior_conflicts),
    )
    write_models_atomic(workspace / "verified_facts.json", outcome.facts)
    write_models_atomic(workspace / CONFLICTS_FILE, [*prior_conflicts, *outcome.concerns])
    kept, cut = split_open_concerns(concerns, questions)
    write_models_atomic(workspace / "concerns.json", kept)
    write_models_atomic(workspace / DROPPED_CONCERNS_FILE, cut)
    write_models_atomic(dropped_path, _merge_dropped(existing, dropped))
    return kept


def _next_number(facts: list[VerifiedFact]) -> int:
    numbers = [int(fact.fact_id[1:]) for fact in facts if fact.fact_id[1:].isdigit()]
    return max(numbers, default=0) + 1


def _as_entries(facts: list[VerifiedFact]) -> list[NotebookEntry]:
    return [
        NotebookEntry(
            entry_id=fact.fact_id,
            statement=fact.statement,
            citations=fact.citations,
            category=fact.category,
        )
        for fact in facts
    ]
