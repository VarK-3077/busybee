"""Cross-document conflict detection: two supported facts that disagree about the same number.

Citation checks cannot catch a conflict, because each fact is supported by its own source
(audited revenue INR 931.2 crore in FY25 versus a news article saying Rs 1,018 crore). This step
runs in `run_verify` after dedupe and id assignment, and the adversary stage calls it again for
facts it added (`only_involving`).

1. `find_conflict_candidates` (deterministic): two live facts of the same category become a
   candidate pair when one of their numbers matches one of the other's on period (FY25 and
   FY2024-25 normalise to the same token, quarter prefixes are kept, "as of <date>" statements
   use the date), unit (non-empty and equal) and metric, yet the values differ by more than
   `MIN_RELATIVE_DIFFERENCE`. Metric matches when the labels are equal or one label's words
   contain the other's ("revenue" vs "revenue operations"), or when the two statements share at
   least `MIN_SHARED_SUBJECT_TOKENS` content words and `MIN_SUBJECT_JACCARD` word overlap
   (two statements that merely mention the same measure in passing are not paired). Negation
   pairs ("no default" vs "default") are deliberately not detected. When both facts carry a
   structured `record`, the comparison is direct: equal metric tokens, period, scope and
   qualifier with canonical values (crore for money) differing by more than the threshold make a
   candidate; no wording similarity is used.
2. `judge_conflicts` (LLM, task `verify_conflict`, at most `BATCH_SIZE` pairs per call): shows each
   pair with the document titles and kinds and replies `{"r":[{"id":1,"conflict":true,
   "metric":".."}]}`, with no note: code builds the note from the two statements. A
   batch whose reply cannot be parsed yields no conflicts, never a guess.
3. `resolve_conflicts`: the fact backed by the higher-authority document kind (financial
   statements > annual report > drhp > rating rationale > covenant > bank statement > news >
   other, the best kind among its citations) is kept and receives a `ConflictNote`; the other
   fact becomes `verification.status = conflicted` (excluded from the report, kept in
   verified_facts.json). Equal authority leaves both facts live, each noting the other with
   `resolved_by="unresolved"`. Every conflict appends a `Concern` (ids CF001...) for the report's
   Open concerns section; `run_verify` writes them to `conflicts.json`.

`detect_and_resolve_conflicts` chains all three; `undo_conflicts_involving` reverses the effects
of removed facts so a re-run of the adversary stage stays idempotent.
"""

import logging
import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from busybee.extract.templates import unit_label
from busybee.ingest.kinds import KIND_PRIORITY
from busybee.llm import Message, Role, StructuredOutputError, complete_as
from busybee.llm.provider import Provider, verify_call_timeout_s
from busybee.schema.documents import Document, DocumentKind
from busybee.schema.facts import (
    ConflictNote,
    NumericValue,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.report import Concern

from .dedupe import jaccard, statement_tokens
from .record_compare import canonical_period, canonical_value, same_measurement

logger = logging.getLogger(__name__)

CONFLICT_TASK = "verify_conflict"
BATCH_SIZE = 10
MIN_RELATIVE_DIFFERENCE = Decimal("0.01")
MIN_SHARED_SUBJECT_TOKENS = 2
MIN_SUBJECT_JACCARD = 0.5
RESOLVED_BY_PRIORITY = "source_priority"
UNRESOLVED = "unresolved"
CONFLICT_CONCERN_PREFIX = "CF"

_KIND_RANK = {kind: index for index, kind in enumerate(KIND_PRIORITY)}
_UNIT_WORDS = frozenset(
    "inr rs rupees crore crores lakh lakhs million billion percent times x".split()
)
_FILLER_WORDS = frozenset(
    "compared against after before during increase decrease increased decreased rose fell "
    "grew growth year previous prior stood reported total about around approximately".split()
)
_GENERIC_LABEL_WORDS = (
    frozenset("value values increase decrease growth total amount number change rise fall".split())
    | _FILLER_WORDS
)
_FISCAL = re.compile(r"\b(?:(q[1-4]|h[12])\s?)?(?:fy|cy)\s?'?(\d{2,4})(?:\s?[-/]\s?(\d{2,4}))?\b")
_AS_OF = re.compile(
    r"\bas\s+(?:of|at|on)\s+(\d{1,2}\s+[a-z]+\s+\d{4}|[a-z]+\s+\d{1,2},?\s+\d{4})", re.IGNORECASE
)
_WORD = re.compile(r"[a-z0-9]+")
_NOTE_WAS = re.compile(r"\(was (\w+)\)")

SYSTEM_PROMPT = (
    "You are a credit analyst checking two statements drawn from different source documents. "
    "For each numbered pair decide whether they CONFLICT: they describe the same metric of the "
    "same entity for the same period but give incompatible numbers. Different metrics, "
    "different periods, different scopes (segment vs total, standalone vs consolidated) or "
    "rounding differences are NOT conflicts. Reply with minified JSON on one line and nothing "
    'else: {"r":[{"id":<pair number>,"conflict":true|false,"metric":"<shared metric>"}]} '
    "with one item per pair; leave metric empty when there is no conflict."
)


@dataclass(frozen=True)
class ConflictCandidate:
    """A pair of facts whose numbers for one metric and period disagree."""

    first_id: str
    second_id: str
    metric: str
    period: str
    values: tuple[Decimal, Decimal]
    unit: str


class PairVerdict(BaseModel):
    """The judge's answer for one numbered pair."""

    model_config = ConfigDict(populate_by_name=True)

    pair: int = Field(alias="id")
    conflict: bool
    metric: str = ""


class ConflictJudgement(BaseModel):
    """The judge's answers for one batch."""

    model_config = ConfigDict(populate_by_name=True)

    results: list[PairVerdict] = Field(default_factory=list, alias="r")


@dataclass(frozen=True)
class ConflictVerdict:
    """A candidate the judge confirmed as a real conflict."""

    candidate: ConflictCandidate
    metric: str
    note: str


@dataclass(frozen=True)
class ConflictOutcome:
    """Updated facts, the new conflict concerns, and how many pairs were examined."""

    facts: list[VerifiedFact]
    concerns: list[Concern]
    candidate_count: int


def normalise_period(period: str) -> str:
    """Canonical period token: FY25, FY2024-25 and FY2025 give 'FY25'; quarters keep 'Q1 FY25'."""
    match = _FISCAL.search(period.lower())
    if match is None:
        return ""
    quarter, first, second = match.groups()
    year = (second or first)[-2:]
    return f"{quarter.upper()} FY{year}" if quarter else f"FY{year}"


def statement_periods(statement: str) -> frozenset[str]:
    """Every normalised fiscal period and 'as of <date>' token named in a statement."""
    periods = {normalise_period(match.group(0)) for match in _FISCAL.finditer(statement.lower())}
    periods.update(
        "as of " + " ".join(_WORD.findall(match.group(1).lower()))
        for match in _AS_OF.finditer(statement)
    )
    periods.discard("")
    return frozenset(periods)


def _number_period(fact: VerifiedFact, number: NumericValue) -> str:
    own = normalise_period(number.period)
    if own:
        return own
    named = statement_periods(fact.statement)
    return next(iter(named)) if len(named) == 1 else ""


def _label_words(label: str) -> frozenset[str]:
    return frozenset(word for word in _WORD.findall(label.lower()) if word not in _UNIT_WORDS)


def _is_generic(words: frozenset[str]) -> bool:
    return not words or words <= _GENERIC_LABEL_WORDS


def labels_match(first: str, second: str) -> bool:
    """True when two non-generic labels are equal or one's words contain the other's."""
    left, right = _label_words(first), _label_words(second)
    if _is_generic(left) or _is_generic(right):
        return False
    return left <= right or right <= left


def _subject_tokens(statement: str) -> frozenset[str]:
    return frozenset(
        word
        for word in statement_tokens(statement)
        if len(word) > 1
        and not word.isdigit()
        and word not in _UNIT_WORDS
        and word not in _FILLER_WORDS
    )


def _differs(first: Decimal, second: Decimal) -> bool:
    largest = max(abs(first), abs(second))
    return largest != 0 and abs(first - second) / largest > MIN_RELATIVE_DIFFERENCE


def _record_candidate(first: VerifiedFact, second: VerifiedFact) -> ConflictCandidate | None:
    left, right = first.record, second.record
    if left is None or right is None or not same_measurement(left, right):
        return None
    (kind, first_size), (other_kind, second_size) = (
        canonical_value(left.value, left.unit),
        canonical_value(right.value, right.unit),
    )
    if kind != other_kind or not _differs(first_size, second_size):
        return None
    return ConflictCandidate(
        first.fact_id,
        second.fact_id,
        left.metric,
        canonical_period(left.period) or left.period,
        (left.value, right.value),
        unit_label(left.unit),
    )


def _pair_candidate(first: VerifiedFact, second: VerifiedFact) -> ConflictCandidate | None:
    if first.record is not None and second.record is not None:
        return _record_candidate(first, second)
    shared = _subject_tokens(first.statement) & _subject_tokens(second.statement)
    same_subject = (
        len(shared) >= MIN_SHARED_SUBJECT_TOKENS
        and jaccard(_subject_tokens(first.statement), _subject_tokens(second.statement))
        >= MIN_SUBJECT_JACCARD
    )
    for left in first.numbers:
        period = _number_period(first, left)
        unit = left.unit.strip()
        if not period or not unit:
            continue
        for right in second.numbers:
            if right.unit.strip() != unit or _number_period(second, right) != period:
                continue
            if not (same_subject or labels_match(left.label, right.label)):
                continue
            if _differs(left.value, right.value):
                metric = " ".join(sorted(shared)) if same_subject else left.label
                return ConflictCandidate(
                    first.fact_id, second.fact_id, metric, period, (left.value, right.value), unit
                )
    return None


def is_conflicted(fact: VerifiedFact) -> bool:
    """True when verification marked the fact as losing a cross-document conflict."""
    return (
        fact.verification is not None and fact.verification.status is VerificationStatus.conflicted
    )


def find_conflict_candidates(
    facts: Sequence[VerifiedFact], only_involving: Collection[str] | None = None
) -> list[ConflictCandidate]:
    """Deterministic candidate pairs among live facts; only_involving restricts to new facts."""
    live = [fact for fact in facts if not is_conflicted(fact)]
    candidates: list[ConflictCandidate] = []
    for first, second in combinations(live, 2):
        if first.category != second.category:
            continue
        if only_involving is not None and not {first.fact_id, second.fact_id} & set(only_involving):
            continue
        candidate = _pair_candidate(first, second)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def source_rank(fact: VerifiedFact, documents: dict[str, Document]) -> int:
    """Authority of a fact: the best (lowest) kind rank among its cited documents."""
    ranks = [_KIND_RANK[documents[c.doc_id].kind] for c in fact.citations if c.doc_id in documents]
    return min(ranks, default=_KIND_RANK[DocumentKind.other])


def _fact_source(fact: VerifiedFact, documents: dict[str, Document]) -> str:
    cited = [documents[c.doc_id] for c in fact.citations if c.doc_id in documents]
    unique = list(dict.fromkeys((doc.title, doc.kind.value) for doc in cited))
    return "; ".join(f"{title}, {kind}" for title, kind in unique) or "unknown document"


def _pair_block(
    number: int,
    candidate: ConflictCandidate,
    by_id: dict[str, VerifiedFact],
    documents: dict[str, Document],
) -> str:
    lines = [f"Pair {number} (period {candidate.period}, unit {candidate.unit})"]
    for tag, fact_id in (("A", candidate.first_id), ("B", candidate.second_id)):
        fact = by_id[fact_id]
        lines.append(f"{tag} [{fact_id}] ({_fact_source(fact, documents)}): {fact.statement}")
    return "\n".join(lines)


def conflict_note(candidate: ConflictCandidate, by_id: dict[str, VerifiedFact]) -> str:
    """The note for a confirmed conflict, built by code from the two statements."""
    first, second = by_id[candidate.first_id], by_id[candidate.second_id]
    return (
        f'{candidate.first_id} states "{first.statement}" while '
        f'{candidate.second_id} states "{second.statement}".'
    )


async def _judge_batch(
    batch: Sequence[ConflictCandidate],
    by_id: dict[str, VerifiedFact],
    documents: dict[str, Document],
    provider: Provider,
) -> list[ConflictVerdict]:
    blocks = [_pair_block(n, c, by_id, documents) for n, c in enumerate(batch, start=1)]
    messages = [
        Message(role=Role.system, content=SYSTEM_PROMPT),
        Message(role=Role.user, content="Pairs\n\n" + "\n\n".join(blocks)),
    ]
    try:
        judgement = await complete_as(
            provider,
            messages,
            ConflictJudgement,
            task=CONFLICT_TASK,
            timeout_s=verify_call_timeout_s(),
        )
    except StructuredOutputError as error:
        logger.warning("conflict judge reply unusable, batch skipped: %s", error)
        return []
    return [
        ConflictVerdict(
            batch[result.pair - 1], result.metric, conflict_note(batch[result.pair - 1], by_id)
        )
        for result in judgement.results
        if result.conflict and 1 <= result.pair <= len(batch)
    ]


async def judge_conflicts(
    candidates: Sequence[ConflictCandidate],
    facts: Iterable[VerifiedFact],
    documents: Iterable[Document],
    provider: Provider,
) -> list[ConflictVerdict]:
    """Ask the judge, BATCH_SIZE pairs per call, which candidates are real conflicts."""
    by_id = {fact.fact_id: fact for fact in facts}
    docs = {doc.doc_id: doc for doc in documents}
    verdicts: list[ConflictVerdict] = []
    for start in range(0, len(candidates), BATCH_SIZE):
        verdicts.extend(
            await _judge_batch(candidates[start : start + BATCH_SIZE], by_id, docs, provider)
        )
    return verdicts


def _conflict_concern(
    number: int, kept: VerifiedFact, other: VerifiedFact, verdict: ConflictVerdict, resolution: str
) -> Concern:
    metric = verdict.metric or verdict.candidate.metric
    return Concern(
        concern_id=f"{CONFLICT_CONCERN_PREFIX}{number:03d}",
        opinion=(
            f"Sources disagree on {metric} for {verdict.candidate.period}: "
            f"{kept.fact_id} versus {other.fact_id}."
        ),
        fact_ids=[kept.fact_id, other.fact_id],
        reasoning=f"{verdict.note} {resolution}".strip(),
        found=False,
        severity="high",
    )


def _demote(fact: VerifiedFact, winner_id: str) -> VerifiedFact:
    old = fact.verification or Verification(status=VerificationStatus.supported)
    notes = f"conflicted with {winner_id} (was {old.status.value}); {old.notes}".strip("; ")
    return fact.model_copy(
        update={
            "verification": old.model_copy(
                update={"status": VerificationStatus.conflicted, "notes": notes}
            )
        }
    )


def _with_note(fact: VerifiedFact, other_id: str, note: str, resolved_by: str) -> VerifiedFact:
    entry = ConflictNote(fact_id=other_id, note=note, resolved_by=resolved_by)
    return fact.model_copy(update={"conflicts": [*fact.conflicts, entry]})


def next_conflict_number(concerns: Iterable[Concern]) -> int:
    """First unused CF number given existing conflict concerns."""
    used = [
        int(c.concern_id[len(CONFLICT_CONCERN_PREFIX) :])
        for c in concerns
        if c.concern_id.startswith(CONFLICT_CONCERN_PREFIX)
        and c.concern_id[len(CONFLICT_CONCERN_PREFIX) :].isdigit()
    ]
    return max(used, default=0) + 1


def resolve_conflicts(
    facts: Sequence[VerifiedFact],
    verdicts: Sequence[ConflictVerdict],
    documents: Iterable[Document],
    start_number: int = 1,
) -> tuple[list[VerifiedFact], list[Concern]]:
    """Apply source priority to confirmed conflicts; return updated facts and new concerns."""
    docs = {doc.doc_id: doc for doc in documents}
    by_id = {fact.fact_id: fact for fact in facts}
    concerns: list[Concern] = []
    for verdict in verdicts:
        first, second = by_id[verdict.candidate.first_id], by_id[verdict.candidate.second_id]
        if is_conflicted(first) or is_conflicted(second):
            continue
        first_rank, second_rank = source_rank(first, docs), source_rank(second, docs)
        note = verdict.note or f"{first.fact_id} and {second.fact_id} disagree."
        if first_rank == second_rank:
            by_id[first.fact_id] = _with_note(first, second.fact_id, note, UNRESOLVED)
            by_id[second.fact_id] = _with_note(second, first.fact_id, note, UNRESOLVED)
            resolution = "Both sources carry equal authority; neither was preferred."
            kept, other = first, second
        else:
            kept, other = (first, second) if first_rank < second_rank else (second, first)
            by_id[kept.fact_id] = _with_note(kept, other.fact_id, note, RESOLVED_BY_PRIORITY)
            by_id[other.fact_id] = _demote(other, kept.fact_id)
            resolution = (
                f"{kept.fact_id} is kept because its source outranks that of {other.fact_id}; "
                f"{other.fact_id} is excluded from the report."
            )
        concerns.append(
            _conflict_concern(start_number + len(concerns), kept, other, verdict, resolution)
        )
    return [by_id[fact.fact_id] for fact in facts], concerns


async def detect_and_resolve_conflicts(
    facts: Sequence[VerifiedFact],
    documents: Sequence[Document],
    provider: Provider,
    *,
    only_involving: Collection[str] | None = None,
    start_number: int = 1,
) -> ConflictOutcome:
    """Find candidates, judge them, resolve by source priority, and build the concerns."""
    candidates = find_conflict_candidates(facts, only_involving)
    if not candidates:
        return ConflictOutcome(list(facts), [], 0)
    verdicts = await judge_conflicts(candidates, facts, documents, provider)
    updated, concerns = resolve_conflicts(facts, verdicts, documents, start_number)
    return ConflictOutcome(updated, concerns, len(candidates))


def undo_conflicts_involving(
    facts: Sequence[VerifiedFact], concerns: Sequence[Concern], removed_ids: Collection[str]
) -> tuple[list[VerifiedFact], list[Concern]]:
    """Undo the effects of removed facts: restore their losers, drop stale notes and concerns."""
    gone = set(removed_ids)
    restored: list[VerifiedFact] = []
    for fact in facts:
        updates: dict[str, object] = {}
        notes = [n for n in fact.conflicts if n.fact_id not in gone]
        if len(notes) != len(fact.conflicts):
            updates["conflicts"] = notes
        verification = fact.verification
        if is_conflicted(fact) and verification is not None:
            winner = re.match(r"conflicted with (\w+)", verification.notes)
            if winner and winner.group(1) in gone:
                was = _NOTE_WAS.search(verification.notes)
                status = VerificationStatus(was.group(1)) if was else VerificationStatus.supported
                updates["verification"] = verification.model_copy(update={"status": status})
        restored.append(fact.model_copy(update=updates) if updates else fact)
    kept = [c for c in concerns if not gone & set(c.fact_ids)]
    return restored, kept
