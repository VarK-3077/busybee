"""Small helpers shared by the metric modules: safe ratios, batching, and chunk text lookup.

`cited_passages` gives the judges the full text of each cited chunk (up to 6000 chars); a longer
chunk is cut to a 3000-char window centred on the cited quote, or on the first statement number
when there is no quote, so the evidence is never silently truncated away.

`judge_halving` runs one batched judge call and, when the reply is cut off by the output-token
limit, splits the batch in half and judges each half, down to single items; an item that still
truncates alone gets the caller's conservative fallback and a logged warning.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence

from busybee.llm import StructuredOutputError
from busybee.schema.documents import Chunk
from busybee.schema.facts import VerifiedFact
from busybee.verify.passage_window import anchor_offset

FULL_CHUNK_CHARS = 6000
WINDOW_CHARS = 3000
JUDGE_TEMPERATURE = 0.0

_log = logging.getLogger(__name__)


def ratio(numerator: int, denominator: int) -> float | None:
    """Return numerator/denominator, or None when there is nothing to measure."""
    return numerator / denominator if denominator else None


def batches_of[ItemT](items: Sequence[ItemT], size: int) -> list[list[ItemT]]:
    """Split items into consecutive batches of at most size."""
    return [list(items[start : start + size]) for start in range(0, len(items), size)]


def passage_for(text: str, quote: str, statement: str) -> str:
    """Return the whole chunk text if short enough, else a window centred on the evidence."""
    if len(text) <= FULL_CHUNK_CHARS:
        return text
    centre = anchor_offset(text, quote, statement)
    start = max(0, min(centre - WINDOW_CHARS // 2, len(text) - WINDOW_CHARS))
    return text[start : start + WINDOW_CHARS]


def cited_passages(fact: VerifiedFact, chunks_by_id: Mapping[str, Chunk]) -> str:
    """Join the text (or evidence window) of every chunk a fact cites."""
    texts = [
        passage_for(chunks_by_id[c.chunk_id].text, c.quote, fact.statement)
        for c in fact.citations
        if c.chunk_id in chunks_by_id
    ]
    return "\n---\n".join(texts) or "(cited chunk unavailable)"


def cited_quotes(fact: VerifiedFact) -> str:
    """Return the fact's cited quotes joined for a judge prompt."""
    return " | ".join(c.quote for c in fact.citations if c.quote) or "(no quote)"


async def judge_halving[ItemT, ResultT](
    batch: Sequence[ItemT],
    judge: Callable[[Sequence[ItemT]], Awaitable[dict[str, ResultT]]],
    fallback: Callable[[ItemT], dict[str, ResultT]],
) -> dict[str, ResultT]:
    """Judge batch; if truncated, judge each half; a lone truncating item gets the fallback."""
    try:
        return await judge(batch)
    except StructuredOutputError as error:
        if not error.truncated:
            raise
        if len(batch) == 1:
            _log.warning("eval judge reply truncated for a single item; using fallback verdict")
            return fallback(batch[0])
    middle = len(batch) // 2
    halves = await asyncio.gather(
        judge_halving(batch[:middle], judge, fallback),
        judge_halving(batch[middle:], judge, fallback),
    )
    return {**halves[0], **halves[1]}
