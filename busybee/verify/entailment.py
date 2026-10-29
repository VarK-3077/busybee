"""LLM entailment judge: does one chunk support a statement, and with which verbatim quote?

The model answers only `{"v":"supported|partial|unsupported","q":"<shortest verbatim span>"}`
(batch: `{"r":[{"id":"<chunk_id>","v":..,"q":..}]}`): no free-text note, to keep replies short.
`EntailmentOutput` is the internal result; its `note` is written by code. The quote is checked in
code: when it is a substring of the chunk (whitespace differences tolerated) it is replaced by the
exact original span; when it is missing or not verbatim, the verdict is kept and the quote becomes
the deterministic span of `quote_span.deterministic_quote` (note "quote located by code"), never a
re-prompt. Exception: a supported verdict for a statement WITHOUT numbers is accepted only when
that span shares at least 60% of the statement's content tokens; otherwise it becomes partial
(note "quote not verbatim and no supporting line found"). A reply whose verdict cannot be parsed
is re-prompted by `complete_as`; if that still
fails the result is unsupported.

Strictness: the prompt demands that every statement number appear literally in the passage with
the same period and unit, and that a value that is inferred, computed, converted or only implied
is `partial`. The deterministic number and period checks in `verify_entries` remain the guard.
Task tag: `verify_entailment`; reply model: `EntailmentReply`.

Several cited chunks are judged in ONE call (`judge_entailment_batch`): every passage is shown
labelled `[chunk_id]` and the reply lists a verdict and quote per chunk id. Each quote is handled
against its own chunk as above; a chunk the reply forgot falls back to the single-chunk judge for
that chunk alone, and a reply that fails structured parsing falls back to one single-chunk call per
chunk. Task tag: `verify_entailment_batch`; reply model: `BatchEntailmentReply`.
"""

import asyncio
import re
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from busybee.llm import Message, Role, StructuredOutputError, complete_as
from busybee.llm.provider import Provider, verify_call_timeout_s
from busybee.verify.number_match import find_numbers
from busybee.verify.quote_span import deterministic_quote, token_overlap

ENTAILMENT_TASK = "verify_entailment"
BATCH_ENTAILMENT_TASK = "verify_entailment_batch"
METHOD_LLM = "llm_entailment"
NOTE_QUOTE_BY_CODE = "quote located by code"
NOTE_NO_SUPPORTING_LINE = "quote not verbatim and no supporting line found"
MIN_LINE_OVERLAP = 0.6

_REPLY_FORMAT = (
    "Reply with minified JSON on one line and nothing else: "
    '{"v":"supported|partial|unsupported","q":"<shortest verbatim span of the passage, at most '
    '160 characters, that contains the key number or phrase>"}. '
    'Use "q":"" when the verdict is unsupported.'
)
_BATCH_REPLY_FORMAT = (
    "Reply with minified JSON on one line and nothing else: "
    '{"r":[{"id":"<chunk_id>","v":"supported|partial|unsupported","q":"<shortest verbatim span '
    'of that passage, at most 160 characters, that contains the key number or phrase>"}]} '
    'with one item per chunk_id. Use "q":"" when the verdict is unsupported.'
)
_SYSTEM = (
    "You verify citations. Given a statement and a source passage, decide whether the passage "
    "supports the statement: 'supported' only if every claim in the statement is stated in the "
    "passage; 'partial' if only some of it is; otherwise 'unsupported'. Every number in the "
    "statement must appear literally in the passage with the same period and the same unit. "
    "Never compute, sum, convert or infer a value: if a value is inferred, computed, converted, "
    "implied or not explicitly stated, the verdict is 'partial' at best. If a value is missing "
    "from the passage, or the passage shows a number without its column or period header so the "
    "period cannot be confirmed, the verdict is 'partial'. For supported or partial, copy the "
    "supporting words from the passage exactly as written (a verbatim substring, no paraphrase) "
    "into the quote. "
    "Metric names: within the same document kind, treat 'revenue from operations', 'operating "
    "income' and 'total income from operations' as the same metric when the passage and the "
    "statement use them interchangeably (rating rationales say operating income). "
    "Direction words: accept 'downgraded', 'upgraded', 'raised' or 'lowered' when the passage's "
    "dated rating history shows that movement, but the dates and grades in the statement must "
    "match the passage literally. "
)
_BATCH_SYSTEM = (
    _SYSTEM
    + "Several source passages are shown, each labelled [chunk_id]. Judge the statement against "
    "EACH passage separately (a passage never gets credit for words that only appear in another "
    "one) and return one item per chunk_id with that passage's own verdict and verbatim quote "
    "from that passage. "
)


class Verdict(StrEnum):
    """How strongly a chunk supports a statement."""

    supported = "supported"
    partial = "partial"
    unsupported = "unsupported"


class EntailmentReply(BaseModel):
    """What the model is asked to produce for one passage: a verdict and a quote."""

    model_config = ConfigDict(populate_by_name=True)

    verdict: Verdict = Field(alias="v")
    quote: str = Field(default="", alias="q")


class ChunkReply(EntailmentReply):
    """The reply item for one labelled passage of a batched call."""

    chunk_id: str = Field(default="", alias="id")


class BatchEntailmentReply(BaseModel):
    """The model's per-chunk replies for one statement."""

    model_config = ConfigDict(populate_by_name=True)

    results: list[ChunkReply] = Field(default_factory=list, alias="r")


class EntailmentOutput(BaseModel):
    """The checked result: verdict, verbatim quote, a code-written note, and the method."""

    verdict: Verdict
    quote: str = ""
    note: str = ""
    method: str = METHOD_LLM


def locate_quote(chunk_text: str, quote: str) -> str | None:
    """Return the exact span of chunk_text matching quote ignoring whitespace, else None."""
    words = quote.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(pattern, chunk_text)
    return match.group(0) if match else None


def checked_output(
    statement: str, verdict: Verdict, quote: str, chunk_text: str
) -> EntailmentOutput:
    """Make the quote verbatim: the exact located span, else the deterministic span of the chunk."""
    if verdict is Verdict.unsupported:
        return EntailmentOutput(verdict=verdict)
    exact = locate_quote(chunk_text, quote)
    if exact is not None:
        return EntailmentOutput(verdict=verdict, quote=exact)
    span = deterministic_quote(statement, chunk_text)
    if (
        verdict is Verdict.supported
        and not find_numbers(statement)
        and token_overlap(statement, span) < MIN_LINE_OVERLAP
    ):
        return EntailmentOutput(verdict=Verdict.partial, quote=span, note=NOTE_NO_SUPPORTING_LINE)
    return EntailmentOutput(verdict=verdict, quote=span, note=NOTE_QUOTE_BY_CODE)


async def judge_entailment(
    statement: str, chunk_text: str, provider: Provider, *, shown: str | None = None
) -> EntailmentOutput:
    """Ask the model whether chunk_text supports statement; quotes are made verbatim by code.

    `shown` is the text put in the prompt when it differs from chunk_text (the same passage
    with `[chunk_id]` labels); quotes are still checked against chunk_text.
    """
    messages = [
        Message(role=Role.system, content=_SYSTEM + _REPLY_FORMAT),
        Message(
            role=Role.user,
            content=f"Statement:\n{statement}\n\nSource passage:\n{shown or chunk_text}",
        ),
    ]
    try:
        reply = await complete_as(
            provider,
            messages,
            EntailmentReply,
            task=ENTAILMENT_TASK,
            timeout_s=verify_call_timeout_s(),
        )
    except StructuredOutputError as error:
        return EntailmentOutput(verdict=Verdict.unsupported, note=f"judge reply unusable: {error}")
    return checked_output(statement, reply.verdict, reply.quote, chunk_text)


def labelled_passages(passages: Sequence[tuple[str, str]]) -> str:
    """Render (chunk_id, text) pairs as `[chunk_id]` headed blocks separated by blank lines."""
    return "\n\n".join(f"[{chunk_id}]\n{text}" for chunk_id, text in passages)


async def judge_entailment_batch(
    statement: str, passages: Sequence[tuple[str, str]], provider: Provider
) -> list[EntailmentOutput]:
    """Judge statement against every (chunk_id, text) passage in one call; one result per passage.

    Results come back in input order. One passage uses the single-chunk judge directly.
    """
    if len(passages) <= 1:
        return [await judge_entailment(statement, text, provider) for _, text in passages]
    messages = [
        Message(role=Role.system, content=_BATCH_SYSTEM + _BATCH_REPLY_FORMAT),
        Message(
            role=Role.user,
            content=f"Statement:\n{statement}\n\nSource passages:\n{labelled_passages(passages)}",
        ),
    ]
    try:
        reply = await complete_as(
            provider,
            messages,
            BatchEntailmentReply,
            task=BATCH_ENTAILMENT_TASK,
            timeout_s=verify_call_timeout_s(),
        )
    except StructuredOutputError:
        return list(
            await asyncio.gather(
                *(judge_entailment(statement, text, provider) for _, text in passages)
            )
        )
    by_id = {item.chunk_id: item for item in reply.results}
    return list(
        await asyncio.gather(
            *(
                _settle(statement, by_id.get(chunk_id), text, provider)
                for chunk_id, text in passages
            )
        )
    )


async def _settle(
    statement: str, judged: ChunkReply | None, text: str, provider: Provider
) -> EntailmentOutput:
    """Check one batched verdict; a chunk the reply forgot goes to the single-chunk judge."""
    if judged is None:
        return await judge_entailment(statement, text, provider)
    return checked_output(statement, judged.verdict, judged.quote, text)
