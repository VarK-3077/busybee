"""Passage-grouped entailment: one LLM call per cited chunk, judging every entry that cites it.

The default LLM verification asked one question per (entry, cited chunks) pair. Here the entries
that survive the deterministic checks (record match, number match, exact statement) are grouped by
cited chunk and each group is judged in ONE call: the passage once, then every statement under a
short local id (`1`, `2`, ...). The model replies with a top-level JSON list of `{"id","v","q"}`
items, the same verdict shape as the single-entry judge; every id is required. Quotes are checked
against the chunk exactly as in `entailment.checked_output`.

An entry citing several chunks is placed in EVERY one of its chunk groups. That keeps today's
semantics: each chunk gets its own verdict and quote, the entry is supported when any chunk
supports it, and all supporting chunks are cited, whichever way the model judged the others.

A group is capped at `MAX_GROUP_ENTRIES` entries and `MAX_GROUP_TOKENS` prompt tokens and split
greedily in input order when larger. Ids that are missing or malformed in a reply are retried once
as a smaller batch (the missing ids, or half the group when nothing usable came back); ids still
missing, and any group whose call fails, fall back to the single-entry call `judge_entailment`.
Calls use the global LLM limiter through the provider and `verify_call_timeout_s`.
`BUSYBEE_VERIFY_BATCH=passage|entry` (default passage) selects this path or the old per-entry one.
Task tag: `verify_entailment_passage`.
"""

import asyncio
import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, RootModel, ValidationError

from busybee.llm import Message, Role, StructuredOutputError, complete_as
from busybee.llm.provider import Provider, verify_call_timeout_s
from busybee.llm.tokens import count_tokens
from busybee.schema.documents import Chunk

from .entailment import _SYSTEM, EntailmentOutput, Verdict, checked_output, judge_entailment

logger = logging.getLogger(__name__)
PASSAGE_TASK = "verify_entailment_passage"
BATCH_ENV = "BUSYBEE_VERIFY_BATCH"
MAX_GROUP_ENTRIES = 25
MAX_GROUP_TOKENS = 8000
_PROMPT_OVERHEAD_TOKENS = 450
_PER_STATEMENT_OVERHEAD_TOKENS = 12
_REPLY_FORMAT = (
    "Reply with minified JSON on one line and nothing else: a top-level list "
    '[{"id":"<statement id>","v":"supported|partial|unsupported","q":"<shortest verbatim span of '
    'the passage, at most 160 characters, that contains the key number or phrase>"}] with exactly '
    'one item per statement id. Use "q":"" when the verdict is unsupported.'
)
_PARTIAL_RULE = (
    "Verdict meaning is the same for every statement: 'supported' when every claim in the "
    "statement is stated in the passage, 'partial' only when part of the statement (a number, "
    "period, unit, entity or qualifier) is absent from or contradicted by the passage. Wording "
    "differences, rounding to the precision the passage shows, lakh/crore conversion of the same "
    "amount and the statement's standard template phrasing (for example 'was INR X as at "
    "<date>') are not grounds for 'partial'. "
)
_SYSTEM_PASSAGE = (
    _SYSTEM
    + "One source passage is shown, followed by several numbered statements. Judge each statement "
    "against the passage independently of the others and return one item per statement id. "
    + _PARTIAL_RULE
)


@dataclass(frozen=True)
class PassageItem:
    """One entry's statement to be judged against one chunk; `key` identifies the entry."""

    key: str
    statement: str


class _Reply(RootModel[list[dict[str, Any]]]):
    pass


class _Item(BaseModel):
    id: str | int
    v: Verdict
    q: str = ""


def passage_batching_enabled() -> bool:
    """True unless BUSYBEE_VERIFY_BATCH is `entry`."""
    return (os.environ.get(BATCH_ENV) or "passage").strip().lower() != "entry"


def _cost(chunk: Chunk, items: Sequence[PassageItem]) -> int:
    return (
        _PROMPT_OVERHEAD_TOKENS
        + count_tokens(chunk.text)
        + sum(count_tokens(i.statement) + _PER_STATEMENT_OVERHEAD_TOKENS for i in items)
    )


def split_group(chunk: Chunk, items: Sequence[PassageItem]) -> list[list[PassageItem]]:
    """Split items greedily in order so no group exceeds the entry and prompt-token caps."""
    groups: list[list[PassageItem]] = []
    current: list[PassageItem] = []
    for item in items:
        if current and (
            len(current) >= MAX_GROUP_ENTRIES or _cost(chunk, [*current, item]) > MAX_GROUP_TOKENS
        ):
            groups.append(current)
            current = []
        current.append(item)
    if current:
        groups.append(current)
    return groups


def _messages(chunk: Chunk, items: Sequence[PassageItem]) -> list[Message]:
    statements = "\n".join(f"{n}. {item.statement}" for n, item in enumerate(items, 1))
    shown = f"Source passage:\n[{chunk.chunk_id}]\n{chunk.text}\n\nStatements:\n{statements}"
    return [
        Message(role=Role.system, content=_SYSTEM_PASSAGE + _REPLY_FORMAT),
        Message(role=Role.user, content=shown),
    ]


async def _ask(chunk: Chunk, items: Sequence[PassageItem], provider: Provider) -> dict[str, _Item]:
    """One call; return the valid items by id (empty when the reply is unusable)."""
    try:
        reply = await complete_as(
            provider,
            _messages(chunk, items),
            _Reply,
            task=PASSAGE_TASK,
            retries=0,
            timeout_s=verify_call_timeout_s(),
        )
    except StructuredOutputError:
        return {}
    except Exception as error:
        logger.warning(
            "passage call for %s failed (%s: %s); falling back to per-entry calls",
            chunk.chunk_id,
            type(error).__name__,
            str(error)[:200],
        )
        return {}
    found: dict[str, _Item] = {}
    for raw in reply.root:
        try:
            item = _Item.model_validate(raw)
        except ValidationError:
            continue
        found.setdefault(str(item.id).strip(), item)
    return found


async def _judge_group(
    chunk: Chunk, items: Sequence[PassageItem], provider: Provider
) -> dict[str, EntailmentOutput]:
    """Judge one capped group: batch call, one smaller retry for missing ids, then singles."""
    verdicts: dict[str, EntailmentOutput] = {}
    remaining = list(items)
    for attempt in range(2):
        if not remaining:
            break
        halves = [remaining]
        if attempt == 1 and len(remaining) == len(items) and len(remaining) > 1:
            middle = len(remaining) // 2
            halves = [remaining[:middle], remaining[middle:]]
        answers = await asyncio.gather(*(_ask(chunk, half, provider) for half in halves))
        for half, answer in zip(halves, answers, strict=True):
            for n, item in enumerate(half, 1):
                got = answer.get(str(n))
                if got is not None:
                    verdicts[item.key] = checked_output(item.statement, got.v, got.q, chunk.text)
        remaining = [item for item in remaining if item.key not in verdicts]
    if remaining:
        singles = await asyncio.gather(
            *(judge_entailment(item.statement, chunk.text, provider) for item in remaining),
            return_exceptions=True,
        )
        for item, out in zip(remaining, singles, strict=True):
            if isinstance(out, EntailmentOutput):
                verdicts[item.key] = out
    return verdicts


async def judge_by_passage(
    entries: Mapping[str, tuple[str, Sequence[Chunk]]], provider: Provider
) -> dict[tuple[str, str], EntailmentOutput]:
    """Judge every entry (key -> (statement, cited chunks)) per chunk; key (entry, chunk_id)."""
    by_chunk: dict[str, tuple[Chunk, list[PassageItem]]] = {}
    for key, (statement, chunks) in entries.items():
        for chunk in chunks:
            by_chunk.setdefault(chunk.chunk_id, (chunk, []))[1].append(PassageItem(key, statement))
    jobs = [
        (chunk, group) for chunk, items in by_chunk.values() for group in split_group(chunk, items)
    ]
    results = await asyncio.gather(*(_judge_group(chunk, group, provider) for chunk, group in jobs))
    out: dict[tuple[str, str], EntailmentOutput] = {}
    for (chunk, _), verdicts in zip(jobs, results, strict=True):
        for key, verdict in verdicts.items():
            out[(key, chunk.chunk_id)] = verdict
    return out
