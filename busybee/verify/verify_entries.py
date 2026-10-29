"""The per-entry verification flow of the verify stage, reusable by the adversary stage.

For a list of notebook entries: (1) one batched relevance pass (optionally pre-filtered by the
reranker, see below) drops entries not useful for a credit-line decision; (2) each kept entry is
checked against its cited chunks - first the
deterministic number match, then an exact-statement match or LLM entailment with a verbatim
quote; (3) an entry whose citation fails is re-cited by searching the vector store with the
statement; if no chunk supports it the entry is dropped as unsupported. When a statement's
numbers are only partly present in the cited chunk, the neighbouring chunks of the same page
(index +-1) are tried: if their union holds every number (each next to a period token when the
statement names a period) and the entailment judge accepts the concatenated passage, all chunks
involved are cited, each with a quote that is a verbatim substring of its own chunk text (the
judge's quote when it lies in that chunk, else the longest line of it that does, else the chunk's
line holding a statement number, else its table header or first line), never the empty string.
An entry citing several chunks gets ONE batched entailment call showing every cited passage
labelled `[chunk_id]` (see entailment.py); the adjacent-chunk path shows its chunks in the same
labelled form. Relevance is skipped for an entry that cites a chunk inside a `[TABLE]` block of
a financial_statements or annual_report document and whose statement mentions a score-input slot
keyword (`VerifyContext.score_keywords`): it is kept with the reason "score input candidate".
With `BUSYBEE_JUDGE=classifier|tiered` the entailment step goes through `judge.py` (classifier
sidecar, windowed to 1,500 chars around the first statement number); a classifier verdict has the
deterministic quote of `quote_span.py` and method `classifier_entailment`, an LLM-resolved band
verdict method `tiered_entailment`. With `BUSYBEE_JUDGE_RELEVANCE=classifier`, entries scoring
below `BUSYBEE_RELEVANCE_MIN` (0.2) against the policy slot lines are dropped without an LLM call.
With `BUSYBEE_VERIFY_BATCH=passage` (default; `entry` keeps the old path) the entries that reach
the LLM entailment step are first judged per cited chunk in `passage_batch.py`, and
`_check_cited_chunks` reads those verdicts (the per-entry call covers any chunk without one).
All entries run concurrently (bounded by the global LLM limiter) and results come back in
input order, so the output is deterministic.
Facts are returned with an empty `fact_id`; `assign_fact_ids` fills it. Every fact figure read
from a table row takes the money unit of its table or page header (`table_units.py`), whatever
the model wrote, so extract and slot-search facts share one deterministic unit rule.

With `progress_path`, each entry's outcome is appended to that file as soon as it is known and
entries already recorded there are reused without any LLM call, so a stage that died halfway
(for example while the LLM server was down) continues where it stopped. Every task is allowed
to finish and an entry whose call still fails after the retry budget (a timeout, a dead
tunnel) is dropped with stage `verify.error`, not recorded in the progress file so a re-run
retries it. The stage raises the first error only when more than 20% of the entries errored.
"""

import asyncio
import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from busybee.extract.templates import record_numbers
from busybee.index.embedder.protocol import Embedder
from busybee.index.store import VectorStore
from busybee.ingest.chunker import chunk_with_prefix
from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk, DocumentKind
from busybee.schema.facts import (
    Citation,
    DroppedEntry,
    NotebookEntry,
    Verification,
    VerificationStatus,
    VerifiedFact,
)

from .entailment import (
    METHOD_LLM,
    EntailmentOutput,
    Verdict,
    judge_entailment,
    judge_entailment_batch,
    labelled_passages,
    locate_quote,
)
from .judge import ClassifierJudge, Decision, Judge, LLMJudge, TieredJudge, judge_from_env
from .number_match import find_numbers, statement_numbers_supported
from .numbers import numeric_values_from
from .passage_batch import judge_by_passage, passage_batching_enabled
from .passage_window import window_around_numbers
from .progress import load_progress, record_outcome, too_many_errors
from .quote_span import deterministic_quote
from .recite import DEFAULT_TOP_K, recite
from .record_match import METHOD_RECORD_MATCH, record_match_quote
from .relevance import BATCH_SIZE, RelevanceDecision, document_summary_lines, judge_relevance
from .table_units import facts_with_header_units

logger = logging.getLogger(__name__)
STAGE_RELEVANCE = "verify.relevance"
STAGE_CITATION = "verify.citation"
STAGE_ERROR = "verify.error"
METHOD_CLASSIFIER = "classifier_entailment"
METHOD_TIERED = "tiered_entailment"
RELEVANCE_JUDGE_ENV = "BUSYBEE_JUDGE_RELEVANCE"
RELEVANCE_MIN_ENV = "BUSYBEE_RELEVANCE_MIN"
DEFAULT_RELEVANCE_MIN = 0.2
METHOD_ADJACENT = "llm_entailment+adjacent_chunks"
REASON_SCORE_INPUT = "score input candidate"
_TABLE_KINDS = frozenset({DocumentKind.financial_statements, DocumentKind.annual_report})
_CHUNK_ID = re.compile(r"^(?P<prefix>.+:p\d+:c)(?P<index>\d+)$")


@dataclass(frozen=True)
class VerifyContext:
    """Everything verification needs: provider, corpus chunks, vector store, embedder, notebook."""

    provider: Provider
    chunks_by_id: Mapping[str, Chunk]
    store: VectorStore | None
    embedder: Embedder | None
    notebook_context: str = ""
    doc_titles: Mapping[str, str] = field(default_factory=dict)
    relevance_context_tokens: int | None = None
    recite_k: int = DEFAULT_TOP_K
    relevance_batch_size: int = BATCH_SIZE
    required_inputs: str = ""
    doc_kinds: Mapping[str, DocumentKind] = field(default_factory=dict)
    score_keywords: tuple[str, ...] = ()
    judge: Judge | None = None
    prejudged: Mapping[tuple[str, str], EntailmentOutput] = field(default_factory=dict)


@dataclass(frozen=True)
class _Outcome:
    fact: VerifiedFact | None = None
    dropped: DroppedEntry | None = None
    error: Exception | None = None


def _squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def _in_table(chunk: Chunk) -> bool:
    return chunk.prefix.startswith("[TABLE") or "[TABLE:" in chunk.text


def is_score_input_candidate(entry: NotebookEntry, ctx: VerifyContext) -> bool:
    """True when the entry cites a table chunk of a statements/report document and names a slot."""
    statement = _squash(entry.statement)
    if not any(keyword in statement for keyword in ctx.score_keywords):
        return False
    for citation in entry.citations:
        chunk = ctx.chunks_by_id.get(citation.chunk_id)
        if chunk is None or ctx.doc_kinds.get(chunk.doc_id) not in _TABLE_KINDS:
            continue
        if _in_table(chunk):
            return True
    return False


def _resolve_chunks(entry: NotebookEntry, ctx: VerifyContext) -> list[Chunk]:
    resolved: list[Chunk] = []
    for citation in entry.citations:
        chunk = ctx.chunks_by_id.get(citation.chunk_id)
        if chunk is not None and chunk not in resolved:
            resolved.append(chunk)
    return resolved


def _citation_for(chunk: Chunk, quote: str) -> Citation:
    return Citation(
        chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no, quote=quote
    )


def _exact_span(statement: str, chunk: Chunk) -> str | None:
    """Return the chunk span equal to the statement (whitespace and case aside), if any."""
    wanted = statement.split()
    if not wanted:
        return None
    pattern = r"\s+".join(re.escape(word) for word in wanted)
    match = re.search(pattern, chunk.text, re.IGNORECASE)
    return match.group(0) if match else None


def _own_quote(chunk: Chunk, quote: str, statement: str) -> str:
    """A verbatim span of this chunk's text standing for the evidence found in it."""
    whole = locate_quote(chunk.text, quote)
    if whole is not None:
        return whole
    for part in sorted(quote.splitlines(), key=len, reverse=True):
        found = locate_quote(chunk.text, part)
        if found is not None:
            return found
    lines = [line.strip() for line in chunk.text.splitlines() if line.strip()]
    for mention in find_numbers(statement):
        for line in lines:
            if mention.text in line:
                return line
    headers = [line for line in lines if line.startswith("[TABLE:")]
    return (headers or lines or [chunk.text.strip()])[0]


def _fact_from(
    entry: NotebookEntry,
    citations: list[Citation],
    status: VerificationStatus,
    method: str,
    notes: str,
) -> VerifiedFact:
    return VerifiedFact(
        fact_id="",
        statement=entry.statement,
        category=entry.category,
        citations=citations,
        numbers=record_numbers(entry.record)
        if entry.record is not None
        else numeric_values_from(entry.statement),
        verification=Verification(status=status, method=method, notes=notes),
        importance=entry.importance,
        source_entry_id=entry.entry_id,
        added_by=entry.added_by,
        record=entry.record,
    )


def _record_match_fact(entry: NotebookEntry, chunks: list[Chunk]) -> VerifiedFact | None:
    """Verify a record entry deterministically against its cited chunks, no LLM involved."""
    if entry.record is None:
        return None
    for chunk in chunks:
        quote = record_match_quote(entry.record, chunk_with_prefix(chunk))
        if quote is not None:
            return _fact_from(
                entry,
                [_citation_for(chunk, quote)],
                VerificationStatus.supported,
                METHOD_RECORD_MATCH,
                "record value, unit, period and label found together in the cited chunk",
            )
    return None


def _neighbour_chunks(chunks: list[Chunk], ctx: VerifyContext) -> list[Chunk]:
    """Return same-page chunks with index one above or below a cited chunk, not yet cited."""
    cited_ids = {chunk.chunk_id for chunk in chunks}
    found: list[Chunk] = []
    for chunk in chunks:
        match = _CHUNK_ID.match(chunk.chunk_id)
        if match is None:
            continue
        index = int(match.group("index"))
        for neighbour_index in (index - 1, index + 1):
            if neighbour_index < 0:
                continue
            neighbour = ctx.chunks_by_id.get(f"{match.group('prefix')}{neighbour_index}")
            if neighbour is not None and neighbour.chunk_id not in cited_ids | {
                c.chunk_id for c in found
            }:
                found.append(neighbour)
    return found


def _by_position(chunks: list[Chunk]) -> list[Chunk]:
    return sorted(chunks, key=lambda c: (c.doc_id, c.page_no, c.index_in_page))


async def _adjacent_chunk_fact(
    entry: NotebookEntry, chunks: list[Chunk], ctx: VerifyContext
) -> VerifiedFact | None:
    """Try the cited chunks plus their same-page neighbours as one concatenated passage."""
    neighbours = _neighbour_chunks(chunks, ctx)
    options = [[n] for n in neighbours]
    if len(neighbours) > 1:
        options.append(neighbours)
    for extra in options:
        involved = _by_position([*chunks, *extra])
        passage = "\n".join(chunk.text for chunk in involved)
        ok, _ = statement_numbers_supported(entry.statement, passage, require_period_adjacency=True)
        if not ok:
            continue
        labelled = labelled_passages([(chunk.chunk_id, chunk.text) for chunk in involved])
        verdict = await judge_entailment(entry.statement, passage, ctx.provider, shown=labelled)
        if verdict.verdict is not Verdict.supported:
            continue
        citations = [
            _citation_for(chunk, _own_quote(chunk, verdict.quote, entry.statement))
            for chunk in involved
        ]
        return _fact_from(
            entry,
            citations,
            VerificationStatus.supported,
            METHOD_ADJACENT,
            "numbers span adjacent chunks of the same page; entailment judged the "
            "concatenated passage as supporting",
        )
    return None


def _decision_quote(entry: NotebookEntry, chunk: Chunk, decision: Decision) -> str:
    if decision.source == "llm" and decision.quote:
        located = locate_quote(chunk.text, decision.quote)
        if located is not None:
            return located
    return deterministic_quote(entry.statement, chunk.text)


async def _judged_fact(
    entry: NotebookEntry, chunks: list[Chunk], judge: Judge
) -> tuple[VerifiedFact | None, str]:
    """Entailment through the Judge: windowed passages, deterministic quotes for the classifier."""
    pairs = [(entry.statement, window_around_numbers(c.text, entry.statement)) for c in chunks]
    decisions = await judge.entailment_batch(pairs)
    supporting = [
        (chunk, decision)
        for chunk, decision in zip(chunks, decisions, strict=True)
        if decision.label == "supported"
    ]
    if supporting:
        by_llm = any(decision.source == "llm" for _, decision in supporting)
        probs = ", ".join(f"{decision.prob:.2f}" for _, decision in supporting)
        return (
            _fact_from(
                entry,
                [_citation_for(c, _decision_quote(entry, c, d)) for c, d in supporting],
                VerificationStatus.supported,
                METHOD_TIERED if by_llm else METHOD_CLASSIFIER,
                f"numbers matched; judge support prob {probs}"
                + ("; uncertain band resolved by the LLM" if by_llm else ""),
            ),
            "",
        )
    probs = ", ".join(f"{decision.prob:.2f}" for decision in decisions)
    return None, f"cited chunks do not support the statement: judge prob {probs}"


async def _check_cited_chunks(
    entry: NotebookEntry, chunks: list[Chunk], ctx: VerifyContext
) -> tuple[VerifiedFact | None, str]:
    """Return the verified fact if the original citations hold, else None and the reason."""
    if not chunks:
        return None, "no cited chunk could be loaded"
    matched = _record_match_fact(entry, chunks)
    if matched is not None:
        return matched, ""
    cited_text = "\n".join(chunk.text for chunk in chunks)
    numbers_ok, missing = statement_numbers_supported(entry.statement, cited_text)
    if not numbers_ok:
        if len(missing) < len(find_numbers(entry.statement)):
            adjacent = await _adjacent_chunk_fact(entry, chunks, ctx)
            if adjacent is not None:
                return adjacent, ""
        return None, f"numbers not found in cited text: {', '.join(missing)}"
    for chunk in chunks:
        span = _exact_span(entry.statement, chunk)
        if span is not None:
            return (
                _fact_from(
                    entry,
                    [_citation_for(chunk, span)],
                    VerificationStatus.supported,
                    "exact_match",
                    "statement appears verbatim in the cited chunk",
                ),
                "",
            )
    if ctx.judge is not None and not isinstance(ctx.judge, LLMJudge):
        return await _judged_fact(entry, chunks, ctx.judge)
    known = [ctx.prejudged.get((entry.entry_id, chunk.chunk_id)) for chunk in chunks]
    if all(verdict is not None for verdict in known):
        verdicts = [verdict for verdict in known if verdict is not None]
    else:
        verdicts = await judge_entailment_batch(
            entry.statement, [(chunk.chunk_id, chunk.text) for chunk in chunks], ctx.provider
        )
    supporting = [
        _citation_for(chunk, verdict.quote)
        for chunk, verdict in zip(chunks, verdicts, strict=True)
        if verdict.verdict is Verdict.supported
    ]
    if supporting:
        return (
            _fact_from(
                entry,
                supporting,
                VerificationStatus.supported,
                METHOD_LLM,
                "numbers matched; entailment judged the cited chunk as supporting",
            ),
            "",
        )
    notes = "; ".join(v.note for v in verdicts if v.note) or "cited chunks do not support it"
    return None, f"cited chunks do not support the statement: {notes}"


def _needs_llm_entailment(entry: NotebookEntry, ctx: VerifyContext) -> list[Chunk] | None:
    """The cited chunks when only the LLM entailment step is left for the entry, else None."""
    chunks = _resolve_chunks(entry, ctx)
    if not chunks or _record_match_fact(entry, chunks) is not None:
        return None
    numbers_ok, _ = statement_numbers_supported(
        entry.statement, "\n".join(chunk.text for chunk in chunks)
    )
    if not numbers_ok or any(_exact_span(entry.statement, c) is not None for c in chunks):
        return None
    return chunks


async def _prejudged_by_passage(
    entries: Sequence[NotebookEntry], kept: list[int], ctx: VerifyContext
) -> VerifyContext:
    """Judge the kept entries that reach the LLM step in passage groups; store the verdicts."""
    if not passage_batching_enabled() or not (ctx.judge is None or isinstance(ctx.judge, LLMJudge)):
        return ctx
    wanted: dict[str, tuple[str, list[Chunk]]] = {}
    for index in kept:
        chunks = _needs_llm_entailment(entries[index], ctx)
        if chunks is not None:
            wanted[entries[index].entry_id] = (entries[index].statement, chunks)
    if not wanted:
        return ctx
    return replace(ctx, prejudged=await judge_by_passage(wanted, ctx.provider))


async def _verify_one(entry: NotebookEntry, ctx: VerifyContext) -> _Outcome:
    chunks = _resolve_chunks(entry, ctx)
    fact, reason = await _check_cited_chunks(entry, chunks, ctx)
    if fact is not None:
        return _Outcome(fact=fact)
    if ctx.store is not None and ctx.embedder is not None:
        found = await recite(
            entry.statement,
            ctx.store,
            ctx.embedder,
            ctx.provider,
            k=ctx.recite_k,
            exclude_chunk_ids={chunk.chunk_id for chunk in chunks},
        )
        if found is not None:
            return _Outcome(
                fact=_fact_from(
                    entry,
                    [_citation_for(found.chunk, found.quote)],
                    VerificationStatus.resupported,
                    "vdb_recite+llm_entailment",
                    f"original citation failed ({reason}); re-cited from the vector store",
                )
            )
    return _Outcome(
        dropped=DroppedEntry(entry=entry, reason=f"unsupported: {reason}", stage=STAGE_CITATION)
    )


async def _verify_and_record(
    entry: NotebookEntry, ctx: VerifyContext, progress_path: Path | None
) -> _Outcome:
    try:
        outcome = await _verify_one(entry, ctx)
    except Exception as error:
        logger.warning(
            "verify of %s failed (%s: %s); dropping it as verify.error",
            entry.entry_id,
            type(error).__name__,
            str(error)[:200],
        )
        return _Outcome(
            dropped=DroppedEntry(
                entry=entry,
                reason=f"error: {type(error).__name__}: {str(error)[:200]}",
                stage=STAGE_ERROR,
            ),
            error=error,
        )
    if progress_path is not None:
        record_outcome(progress_path, entry, fact=outcome.fact, dropped=outcome.dropped)
    return outcome


async def _classifier_relevance_drops(
    entries: Sequence[NotebookEntry], indexes: list[int], ctx: VerifyContext, check_relevance: bool
) -> tuple[dict[str, RelevanceDecision], list[int]]:
    """Drop entries the reranker scores below BUSYBEE_RELEVANCE_MIN; the rest go on to the LLM."""
    wanted = os.environ.get(RELEVANCE_JUDGE_ENV, "").strip().lower() == "classifier"
    if not (wanted and check_relevance and indexes and ctx.required_inputs.strip()):
        return {}, indexes
    judge = ctx.judge if isinstance(ctx.judge, ClassifierJudge | TieredJudge) else ClassifierJudge()
    try:
        floor = float(os.environ.get(RELEVANCE_MIN_ENV, ""))
    except ValueError:
        floor = DEFAULT_RELEVANCE_MIN
    try:
        scores = await judge.relevance_batch(
            [entries[index].statement for index in indexes], ctx.required_inputs
        )
    except Exception as error:
        logger.warning(
            "classifier relevance failed (%s: %s); the LLM relevance pass decides instead",
            type(error).__name__,
            str(error)[:200],
        )
        return {}, indexes
    dropped: dict[str, RelevanceDecision] = {}
    remaining: list[int] = []
    for index, score in zip(indexes, scores, strict=True):
        if score < floor:
            entry_id = entries[index].entry_id
            reason = f"classifier relevance {score:.2f} below {floor:.2f}"
            dropped[entry_id] = RelevanceDecision(entry_id=entry_id, keep=False, reason=reason)
        else:
            remaining.append(index)
    return dropped, remaining


async def verify_entries(
    entries: Sequence[NotebookEntry],
    ctx: VerifyContext,
    *,
    check_relevance: bool = True,
    progress_path: Path | None = None,
) -> tuple[list[VerifiedFact], list[DroppedEntry]]:
    """Verify entries; return (verified facts, dropped entries), both in input order."""
    outcomes: dict[int, _Outcome] = {}
    if ctx.judge is None and (os.environ.get("BUSYBEE_JUDGE") or "llm").strip().lower() != "llm":
        ctx = replace(ctx, judge=judge_from_env(ctx.provider))
    if progress_path is not None:
        saved = load_progress(progress_path, entries)
        for index, entry in enumerate(entries):
            record = saved.get(entry.entry_id)
            if record is not None:
                outcomes[index] = _Outcome(fact=record.fact, dropped=record.dropped)
    pending = [index for index in range(len(entries)) if index not in outcomes]
    auto = {
        entries[index].entry_id: RelevanceDecision(
            entry_id=entries[index].entry_id, keep=True, reason=REASON_SCORE_INPUT
        )
        for index in pending
        if check_relevance and is_score_input_candidate(entries[index], ctx)
    }
    to_judge = [index for index in pending if entries[index].entry_id not in auto]
    low_relevance, to_judge = await _classifier_relevance_drops(
        entries, to_judge, ctx, check_relevance
    )
    auto = auto | low_relevance
    decisions = (
        await judge_relevance(
            [entries[index] for index in to_judge],
            ctx.notebook_context,
            ctx.provider,
            batch_size=ctx.relevance_batch_size,
            required_inputs=ctx.required_inputs,
            notebook=entries,
            summary_lines=document_summary_lines(entries, ctx.doc_titles, ctx.doc_kinds),
            context_tokens=ctx.relevance_context_tokens,
        )
        if check_relevance and to_judge
        else {}
    ) | auto
    kept: list[int] = []
    for index in pending:
        entry = entries[index]
        decision = decisions.get(entry.entry_id)
        if decision is not None and not decision.keep:
            reason = decision.reason or "judged not relevant"
            dropped = DroppedEntry(
                entry=entry, reason=f"not relevant: {reason}", stage=STAGE_RELEVANCE
            )
            outcomes[index] = _Outcome(dropped=dropped)
            if progress_path is not None:
                record_outcome(progress_path, entry, dropped=dropped)
        else:
            kept.append(index)
    ctx = await _prejudged_by_passage(entries, kept, ctx)
    results = await asyncio.gather(
        *(_verify_and_record(entries[index], ctx, progress_path) for index in kept),
        return_exceptions=True,
    )
    for index, result in zip(kept, results, strict=True):
        if isinstance(result, BaseException):
            raise result
        outcomes[index] = result
    errors = [result.error for result in results if result.error is not None]
    if errors and too_many_errors(len(errors), len(kept)):
        raise errors[0]
    facts: list[VerifiedFact] = []
    dropped_entries: list[DroppedEntry] = []
    for index in range(len(entries)):
        outcome = outcomes[index]
        if outcome.fact is not None:
            facts.append(outcome.fact)
        elif outcome.dropped is not None:
            dropped_entries.append(outcome.dropped)
    return facts_with_header_units(facts, ctx.chunks_by_id), dropped_entries
