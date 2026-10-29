"""Incident: one LLM call timing out after the retry budget must not kill the verify stage."""

import re
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest

from busybee.llm import Completion, Message
from busybee.verify.progress import PROGRESS_FILE, load_progress
from busybee.verify.verify_entries import VerifyContext, verify_entries

from .helpers import judge_provider, make_chunk, make_entry

CHUNK = make_chunk("D1:p1:c0", "Revenue for FY24 was Rs 1,200 crore.")
REQUEST = httpx.Request("POST", "http://127.0.0.1:8000/v1/chat/completions")


class TimingOutProvider:
    """Scripted judge that raises a timeout for statements containing a bad marker."""

    name = "timing-out"
    model = "timing-out"

    def __init__(self, bad: set[str], error: Exception, relevance_error: bool = False) -> None:
        self.inner = judge_provider(supports=lambda statement, passage: True)
        self.bad = bad
        self.error = error
        self.relevance_error = relevance_error

    async def complete(self, messages: list[Message], **kwargs: Any) -> Completion:
        if kwargs.get("task") == "verify_entailment":
            found = re.search(r"Statement:\n(.*)\n\nSource passage", messages[-1].content)
            assert found is not None
            if any(name in found.group(1) for name in self.bad):
                raise self.error
        if kwargs.get("task") == "verify_relevance" and self.relevance_error:
            raise self.error
        return await self.inner.complete(messages, **kwargs)


def make_entries(count: int):  # noqa: ANN201
    return [
        make_entry(f"E{i}", f"Revenue for FY24 was Rs 1,200 crore (variant n{i}n)")
        for i in range(count)
    ]


def make_ctx(provider: TimingOutProvider) -> VerifyContext:
    return VerifyContext(
        provider=provider, chunks_by_id={CHUNK.chunk_id: CHUNK}, store=None, embedder=None
    )


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=REQUEST),
        httpx.ReadTimeout("read timed out"),
    ],
)
async def test_a_timed_out_entry_is_dropped_as_verify_error(
    tmp_path: Path, error: Exception
) -> None:
    provider = TimingOutProvider({"n3n"}, error)
    progress = tmp_path / PROGRESS_FILE
    entries = make_entries(10)

    facts, dropped = await verify_entries(entries, make_ctx(provider), progress_path=progress)

    assert len(facts) == 9
    assert [d.entry.entry_id for d in dropped] == ["E3"]
    assert dropped[0].stage == "verify.error"
    assert type(error).__name__ in dropped[0].reason
    recorded = load_progress(progress, entries)
    assert len(recorded) == 9
    assert "E3" not in recorded


async def test_a_systemic_outage_still_fails_the_stage(tmp_path: Path) -> None:
    provider = TimingOutProvider({"n1n", "n2n", "n3n"}, openai.APITimeoutError(request=REQUEST))
    progress = tmp_path / PROGRESS_FILE
    entries = make_entries(10)

    with pytest.raises(openai.APITimeoutError):
        await verify_entries(entries, make_ctx(provider), progress_path=progress)

    assert len(load_progress(progress, entries)) == 7


async def test_a_failed_relevance_batch_keeps_its_entries() -> None:
    provider = TimingOutProvider(set(), openai.APITimeoutError(request=REQUEST), True)
    ctx = make_ctx(provider)
    with pytest.raises(openai.APITimeoutError):
        await verify_entries(make_entries(3), ctx)

    from busybee.verify.relevance import batches_of, judge_relevance

    entries = make_entries(100)
    assert len(batches_of(entries, 40)) == 3
    calls = 0
    inner = provider.inner

    class OneBatchFails:
        name = model = "x"

        async def complete(self, messages: list[Message], **kwargs: Any) -> Completion:
            nonlocal calls
            calls += 1
            if calls == 1 and kwargs.get("task") == "verify_relevance":
                raise openai.APITimeoutError(request=REQUEST)
            return await inner.complete(messages, **kwargs)

    many = make_entries(400)
    decisions = await judge_relevance(many, "", OneBatchFails(), batch_size=40)
    assert len(decisions) == 400
    assert sum(1 for d in decisions.values() if "unavailable" in d.reason) == 40
