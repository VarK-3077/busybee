"""LLM matching of gold facts against report facts, with a deterministic shared-number prefilter.

For each gold fact only report facts that share a distinctive number with it (or, when the
gold statement has no usable numbers, share enough content words) are shown to the judge,
which keeps prompts small and the candidate set reproducible. Years (two-digit and
four-digit) and numbers that occur in more than a quarter of the report facts carry no
signal and are ignored in the overlap score; money amounts are compared in canonical crore
(lakh, million, billion converted, rounding tolerated); ties fall back to content-word overlap. Gold
facts with no candidates are unmatched without any LLM call. The rest go to the model in
batches asking, per gold fact, which candidates (one or several) jointly state the same
thing with the same numbers: a gold fact is covered by the union of the listed facts.
Task tag: `eval_match`; response model: `MatchOutput`; temperature 0.
"""

import asyncio
import re
from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from busybee.eval.metrics.common import JUDGE_TEMPERATURE, judge_halving
from busybee.llm import Message, Role, complete_as
from busybee.llm.provider import Provider
from busybee.schema.facts import VerifiedFact
from busybee.verify.number_match import find_numbers
from busybee.verify.numbers import amounts_match, canonical_amount

MATCH_TASK = "eval_match"
BATCH_SIZE = 8
MAX_CANDIDATES = 8
COMMON_NUMBER_SHARE = 0.25
MIN_FACTS_FOR_COMMON_FILTER = 20
_WORD = re.compile(r"[a-z]{4,}")

_SYSTEM = (
    "You compare gold reference statements with candidate statements from a credit report. "
    "A gold statement counts as present if its content and its key numbers are jointly covered "
    "by one or more of the listed candidate facts; several candidates may each state a part. "
    "The candidates together must not contradict the gold statement or change a number. For "
    "every gold id answer with the list of candidate fact ids that cover it, or an empty list "
    'when it is not covered. The gold id is the bare number after GOLD, for example "0".'
)


class MatchDecision(BaseModel):
    """The judge's answer for one gold fact: the covering fact ids, empty when unmatched."""

    gold_id: str
    fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_single_fact_id(cls, data: object) -> object:
        if isinstance(data, dict) and "fact_ids" not in data and "fact_id" in data:
            single = data["fact_id"]
            return {"gold_id": data.get("gold_id", ""), "fact_ids": [single] if single else []}
        return data


class MatchOutput(BaseModel):
    """The model reply for one batch of gold facts."""

    matches: list[MatchDecision] = Field(default_factory=list)


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _is_year_like(value: Decimal) -> bool:
    if value != value.to_integral_value():
        return False
    return 10 <= value <= 99 or 1900 <= value <= 2100


def _signature(text: str) -> tuple[set[Decimal], set[Decimal]]:
    """Return (plain absolute numbers, money amounts in canonical crore) found in text."""
    plain: set[Decimal] = set()
    amounts: set[Decimal] = set()
    for mention in find_numbers(text):
        for value in mention.alternatives[:1] if not mention.fiscal else mention.alternatives:
            plain.add(abs(value))
        canonical = canonical_amount(mention.value, mention.unit) if mention.unit else None
        if canonical is not None:
            amounts.add(abs(canonical[1]))
    return plain, amounts


def _common_values(facts: Sequence[VerifiedFact]) -> set[Decimal]:
    if len(facts) < MIN_FACTS_FOR_COMMON_FILTER:
        return set()
    counts: dict[Decimal, int] = {}
    for fact in facts:
        plain, amounts = _signature(fact.statement)
        for value in plain | amounts:
            counts[value] = counts.get(value, 0) + 1
    limit = COMMON_NUMBER_SHARE * len(facts)
    return {value for value, count in counts.items() if count > limit}


def _informative(text: str, common: set[Decimal]) -> tuple[set[Decimal], set[Decimal]]:
    plain, amounts = _signature(text)
    return (
        {v for v in plain if not _is_year_like(v) and v not in common},
        {v for v in amounts if v not in common},
    )


def _shared_numbers(
    wanted: tuple[set[Decimal], set[Decimal]], have: tuple[set[Decimal], set[Decimal]]
) -> int:
    """Count shared plain numbers plus amounts equal in crore within rounding tolerance."""
    plain = len(wanted[0] & have[0])
    amounts = sum(1 for w in wanted[1] if any(amounts_match(w, h) for h in have[1]))
    return plain + amounts


def candidate_facts(statement: str, facts: Sequence[VerifiedFact]) -> list[VerifiedFact]:
    """Return report facts sharing distinctive numbers (or content words), best first.

    Money amounts are compared in crore, so "9,868.39 lakhs" meets "98.67 crore".
    """
    common = _common_values(facts)
    wanted = _informative(statement, common)
    gold_words = _words(statement)
    scored: list[tuple[int, int, int, VerifiedFact]] = []
    for position, fact in enumerate(facts):
        shared_words = len(gold_words & _words(fact.statement))
        if wanted[0] or wanted[1]:
            overlap = _shared_numbers(wanted, _informative(fact.statement, common))
        else:
            overlap = shared_words if shared_words >= 3 else 0
        if overlap:
            scored.append((-overlap, -shared_words, position, fact))
    scored.sort(key=lambda item: item[:3])
    return [fact for *_, fact in scored[:MAX_CANDIDATES]]


def _bare_id(gold_id: str) -> str:
    """Accept `0`, `GOLD 0` or `GOLD 0:` as the gold id 0 (models echo the block header)."""
    found = re.search(r"\d+", gold_id)
    return found.group(0) if found else gold_id.strip()


def _block(gold_id: str, statement: str, candidates: Sequence[VerifiedFact]) -> str:
    lines = [f"GOLD {gold_id}: {' '.join(statement.split())}"]
    lines.extend(f"  - {c.fact_id}: {' '.join(c.statement.split())}" for c in candidates)
    return "\n".join(lines)


def build_match_messages(blocks: Sequence[str]) -> list[Message]:
    """Build the prompt for one batch of gold facts with their candidates."""
    return [
        Message(role=Role.system, content=_SYSTEM),
        Message(role=Role.user, content="\n\n".join(blocks)),
    ]


async def _match_once(
    batch: Sequence[tuple[str, str, list[VerifiedFact]]], provider: Provider
) -> dict[str, list[str]]:
    blocks = [_block(gold_id, statement, found) for gold_id, statement, found in batch]
    output = await complete_as(
        provider,
        build_match_messages(blocks),
        MatchOutput,
        task=MATCH_TASK,
        temperature=JUDGE_TEMPERATURE,
    )
    allowed = {gold_id: {c.fact_id for c in found} for gold_id, _, found in batch}
    matched: dict[str, list[str]] = {}
    for decision in output.matches:
        gold_id = _bare_id(decision.gold_id)
        ids = list(dict.fromkeys(decision.fact_ids))
        if ids and all(fid in allowed.get(gold_id, set()) for fid in ids):
            matched[gold_id] = ids
    return matched


def _unmatched(item: tuple[str, str, list[VerifiedFact]]) -> dict[str, list[str]]:
    return {}


async def _match_batch(
    batch: Sequence[tuple[str, str, list[VerifiedFact]]], provider: Provider
) -> dict[str, list[str]]:
    return await judge_halving(batch, lambda part: _match_once(part, provider), _unmatched)


async def match_statements(
    statements: Sequence[str],
    facts: Sequence[VerifiedFact],
    provider: Provider,
    *,
    batch_size: int = BATCH_SIZE,
) -> dict[int, list[str]]:
    """Map each statement index to the report fact ids jointly covering it (empty = unmatched)."""
    work = [
        (str(index), statement, candidate_facts(statement, facts))
        for index, statement in enumerate(statements)
    ]
    work = [item for item in work if item[2]]
    batches = [work[start : start + batch_size] for start in range(0, len(work), batch_size)]
    results = await asyncio.gather(*(_match_batch(batch, provider) for batch in batches))
    merged: dict[str, list[str]] = {}
    for result in results:
        merged.update(result)
    return {index: merged.get(str(index), []) for index in range(len(statements))}
