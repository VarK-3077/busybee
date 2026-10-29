"""Batched LLM relevance filter: keep or drop each notebook entry for a credit-line decision.

Entries go to the model in batches of at most `BATCH_SIZE` (40). Each batch carries a compact
context (see `build_batch_context`): one summary line per document, then the condensed entries of
the batch's own documents plus entries sharing at least two content tokens with the batch, capped
at `relevance_context_tokens` (default 6000, env BUSYBEE_RELEVANCE_CONTEXT_TOKENS) by dropping
the lowest-importance entries first, so duplicates can be recognised without sending the whole
notebook every time. Batches run
concurrently (the global limiter bounds real parallelism).

The model replies only with the entries to drop, each with a reason code:
`{"drop":[["E012","dup"],["E019","trivia"]]}` (codes in `DROP_REASONS`: dup, trivia, admin,
offtopic, stale). Every entry not listed is kept with reason "kept"; dropping needs an explicit
listed id, never silence. `RelevanceDecision.reason` carries the human-readable expansion of the
code (`DROP_REASONS`), so dropped.json and the audit trail stay readable.
A `dup` drop is only honoured when a kept entry is its twin (`keep_lone_duplicates`): an entry
sharing its largest figure and two content words, or for an entry without figures most of its
words. Batches are judged apart, so every copy of a figure can be called a duplicate of another
copy and none survive (all consolidated cash and finance-cost rows of a pack); the first copy of
such a group is then kept, and `dedupe_facts` merges the copies after verification as usual.
Task tag: `verify_relevance`; reply model: `RelevanceReply`.
"""

import asyncio
import logging
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal

from pydantic import BaseModel, Field

from busybee.extract.condensed import condense_entry
from busybee.llm import Message, Role, complete_as
from busybee.llm.provider import Provider, verify_call_timeout_s
from busybee.llm.tokens import count_tokens, truncate_to_tokens
from busybee.schema.facts import NotebookEntry

from .number_match import extract_numbers
from .progress import too_many_errors

logger = logging.getLogger(__name__)

BATCH_SIZE = 40
RELEVANCE_TASK = "verify_relevance"
CONTEXT_TOKENS_ENV = "BUSYBEE_RELEVANCE_CONTEXT_TOKENS"
DEFAULT_CONTEXT_TOKENS = 6000
MIN_SHARED_TOKENS = 2
_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP_WORDS = frozenset(
    "the and for with that this from were was are has had have its our their which been "
    "during into over than also not but per all any may can will year years company".split()
)

DROP_REASONS = {
    "dup": "duplicate of another entry",
    "trivia": "immaterial detail",
    "admin": "corporate or administrative boilerplate",
    "offtopic": "not about the borrower's credit",
    "stale": "superseded older period with a newer equivalent entry",
}
KEPT_REASON = "kept"
UNAVAILABLE_REASON = "relevance judge unavailable; kept for verification"
LONE_DUPLICATE_REASON = "called a duplicate but no kept entry states it; kept"
_TWIN_OVERLAP = 0.6
_REPLY_FORMAT = (
    "\n\nReply with minified JSON on one line listing ONLY the entries to drop, each with a "
    'reason code: {"drop":[["E012","dup"],["E019","trivia"]]}. Codes: '
    + "; ".join(f"{code} = {meaning}" for code, meaning in DROP_REASONS.items())
    + '. Every entry you do not list is kept. If nothing is dropped reply {"drop":[]}.'
)

_SYSTEM = (
    "You are a credit analyst deciding which extracted facts belong in a credit-review report "
    "used to size a credit line for a borrower. Keep facts that bear on repayment capacity, "
    "leverage, liquidity, credit history, ratings, governance, litigation, or industry risk. "
    "Always keep dividends declared or recommended (even by a loss-making company), buybacks "
    "and other cash outflows, and any item that the scoring-policy slot descriptions mention. "
    "Drop boilerplate, marketing language, and trivia, and administrative lines such as book "
    "closure, record date, IEPF and e-payment instructions. Use dup only for a repeat of the same "
    "fact from the same document; a repeat in a different document is a second citation, so "
    "keep it (code merges duplicates afterwards). Use stale only when the notebook shows a newer "
    "equivalent entry for a later period."
)
_REQUIRED_INPUTS = (
    "\n\nThe bank's scoring policy needs these inputs. Always keep an entry that states any "
    "of them (including a derived figure, a rating index or a red-flag count), even if it "
    "seems minor, a repeat, or forward-looking:\n"
)


class RelevanceDecision(BaseModel):
    """Keep or drop verdict for one notebook entry."""

    entry_id: str
    keep: bool
    reason: str = ""


class RelevanceReply(BaseModel):
    """The model reply for one batch: the entries to drop, as [entry_id, reason_code] pairs."""

    drop: list[list[str]] = Field(default_factory=list)


def drop_reason(code: str) -> str:
    """Human-readable expansion of a reason code; an unknown code is kept as written."""
    cleaned = code.strip().casefold()
    return DROP_REASONS.get(cleaned, cleaned or "dropped by relevance filter")


def batches_of[ItemT](items: Sequence[ItemT], size: int = BATCH_SIZE) -> list[list[ItemT]]:
    """Split items into consecutive batches of at most size."""
    return [list(items[start : start + size]) for start in range(0, len(items), size)]


def relevance_context_tokens() -> int:
    """The per-batch context cap from BUSYBEE_RELEVANCE_CONTEXT_TOKENS, else 6000."""
    try:
        value = int(os.environ.get(CONTEXT_TOKENS_ENV, ""))
    except ValueError:
        return DEFAULT_CONTEXT_TOKENS
    return value if value > 0 else DEFAULT_CONTEXT_TOKENS


def _content_tokens(entry: NotebookEntry) -> frozenset[str]:
    return frozenset(_WORD.findall(entry.statement.casefold())) - _STOP_WORDS


def document_summary_lines(
    entries: Sequence[NotebookEntry],
    doc_titles: Mapping[str, str],
    doc_kinds: Mapping[str, str],
) -> list[str]:
    """One line per document: id, title, kind and the number of entries in each category."""
    counts: dict[str, Counter[str]] = {}
    for entry in entries:
        counts.setdefault(entry.doc_id, Counter())[entry.category.value] += 1
    doc_ids = [*doc_titles, *(doc_id for doc_id in counts if doc_id not in doc_titles)]
    lines = []
    for doc_id in doc_ids:
        by_category = counts.get(doc_id, Counter())
        mix = ", ".join(f"{name}={n}" for name, n in sorted(by_category.items())) or "no entries"
        title = " ".join(doc_titles.get(doc_id, "").split())
        lines.append(f"{doc_id or '(none)'} | {title} | {doc_kinds.get(doc_id, 'other')} | {mix}")
    return lines


def build_batch_context(
    batch: Sequence[NotebookEntry],
    entries: Sequence[NotebookEntry],
    summary_lines: Sequence[str],
    max_tokens: int,
) -> str:
    """Summary lines plus the related condensed entries, never above max_tokens.

    Related means same document as a batch entry, or at least two shared content tokens with one.
    Entries are dropped lowest importance first (other-document entries before same-document
    ones on ties); survivors are shown in notebook order.
    """
    summary = truncate_to_tokens("\n".join(summary_lines), max_tokens // 2)
    budget = max_tokens - count_tokens(summary) - 8
    batch_ids = {entry.entry_id for entry in batch}
    batch_docs = {entry.doc_id for entry in batch}
    batch_tokens = [_content_tokens(entry) for entry in batch]
    candidates: list[tuple[int, bool, int, str]] = []
    for index, entry in enumerate(entries):
        if entry.entry_id in batch_ids:
            continue
        same_doc = entry.doc_id in batch_docs
        if not same_doc:
            words = _content_tokens(entry)
            if not any(len(words & other) >= MIN_SHARED_TOKENS for other in batch_tokens):
                continue
        candidates.append((entry.importance, same_doc, index, condense_entry(entry)))
    candidates.sort(key=lambda item: (-item[0], not item[1], item[2]))
    chosen: list[tuple[int, str]] = []
    for _, _, index, line in candidates:
        cost = count_tokens(line) + 1
        if cost > budget:
            continue
        budget -= cost
        chosen.append((index, line))
    chosen.sort()
    return "\n".join([summary, *(line for _, line in chosen)]) if chosen else summary


def _entry_block(entry: NotebookEntry) -> str:
    statement = " ".join(entry.statement.split())
    return f"- {entry.entry_id} | {entry.category.value} | imp {entry.importance} | {statement}"


def build_relevance_messages(
    batch: Sequence[NotebookEntry], context: str, required_inputs: str = ""
) -> list[Message]:
    """Build the prompt for one batch; required_inputs lists the policy inputs to protect."""
    system = (
        _SYSTEM + (_REQUIRED_INPUTS + required_inputs if required_inputs else "") + _REPLY_FORMAT
    )
    listing = "\n".join(_entry_block(entry) for entry in batch)
    return [
        Message(role=Role.system, content=system),
        Message(
            role=Role.user,
            content=(
                f"Condensed notebook (context only):\n{context or '(empty)'}\n\n"
                f"Decide on exactly these entries:\n{listing}"
            ),
        ),
    ]


async def _judge_batch(
    batch: Sequence[NotebookEntry], context: str, provider: Provider, required_inputs: str
) -> dict[str, RelevanceDecision]:
    reply = await complete_as(
        provider,
        build_relevance_messages(batch, context, required_inputs),
        RelevanceReply,
        task=RELEVANCE_TASK,
        timeout_s=verify_call_timeout_s(),
    )
    wanted = {entry.entry_id for entry in batch}
    decided = {
        entry.entry_id: RelevanceDecision(entry_id=entry.entry_id, keep=True, reason=KEPT_REASON)
        for entry in batch
    }
    for item in reply.drop:
        entry_id = item[0].strip() if item else ""
        if entry_id in wanted:
            code = item[1] if len(item) > 1 else ""
            decided[entry_id] = RelevanceDecision(
                entry_id=entry_id, keep=False, reason=drop_reason(code)
            )
    return decided


async def judge_relevance(
    entries: Sequence[NotebookEntry],
    context: str,
    provider: Provider,
    *,
    batch_size: int = BATCH_SIZE,
    required_inputs: str = "",
    notebook: Sequence[NotebookEntry] | None = None,
    summary_lines: Sequence[str] = (),
    context_tokens: int | None = None,
) -> dict[str, RelevanceDecision]:
    """Return a decision for every entry id, using batched concurrent LLM calls.

    With notebook given, each batch gets its own `build_batch_context`; otherwise the fixed
    context string is sent to every batch.
    """
    cap = context_tokens if context_tokens is not None else relevance_context_tokens()

    def context_for(batch: Sequence[NotebookEntry]) -> str:
        if notebook is None:
            return context
        return build_batch_context(batch, notebook, summary_lines, cap)

    batches = batches_of(entries, batch_size)
    results = await asyncio.gather(
        *(_judge_batch(batch, context_for(batch), provider, required_inputs) for batch in batches),
        return_exceptions=True,
    )
    failures = [result for result in results if isinstance(result, Exception)]
    if too_many_errors(len(failures), len(batches)):
        raise failures[0]
    merged: dict[str, RelevanceDecision] = {}
    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(
                "relevance batch of %d entries failed (%s: %s); keeping them",
                len(batch),
                type(result).__name__,
                str(result)[:200],
            )
            merged.update(
                {
                    entry.entry_id: RelevanceDecision(
                        entry_id=entry.entry_id, keep=True, reason=UNAVAILABLE_REASON
                    )
                    for entry in batch
                }
            )
        elif isinstance(result, BaseException):
            raise result
        else:
            merged.update(result)
    return keep_lone_duplicates(entries, merged)


def _figures(entry: NotebookEntry) -> set[Decimal]:
    values = {abs(value) for value in extract_numbers(entry.statement)}
    return {
        value
        for value in values
        if not (value == value.to_integral() and (value <= 31 or 1900 <= value <= 2100))
    }


def _is_twin(entry: NotebookEntry, other: NotebookEntry) -> bool:
    mine, theirs = _content_tokens(entry), _content_tokens(other)
    figures = _figures(entry)
    if figures:
        return max(figures) in _figures(other) and len(mine & theirs) >= MIN_SHARED_TOKENS
    union = mine | theirs
    return bool(union) and len(mine & theirs) / len(union) >= _TWIN_OVERLAP


def keep_lone_duplicates(
    entries: Sequence[NotebookEntry], decisions: dict[str, RelevanceDecision]
) -> dict[str, RelevanceDecision]:
    """Keep each entry dropped as a duplicate when no kept entry is its twin, first copy first."""
    duplicate = DROP_REASONS["dup"]
    kept = [
        entry for entry in entries if (found := decisions.get(entry.entry_id)) is None or found.keep
    ]
    result = dict(decisions)
    for entry in entries:
        decision = result.get(entry.entry_id)
        if decision is None or decision.keep or decision.reason != duplicate:
            continue
        if any(_is_twin(entry, other) for other in kept):
            continue
        result[entry.entry_id] = RelevanceDecision(
            entry_id=entry.entry_id, keep=True, reason=LONE_DUPLICATE_REASON
        )
        kept.append(entry)
    return result
