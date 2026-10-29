"""Passage-grouped entailment: grouping, splitting, retries, fallback, multi-chunk, env switch."""

import json
import re

import pytest

from busybee.llm import MockProvider
from busybee.schema.facts import Citation, NotebookEntry
from busybee.verify import passage_batch
from busybee.verify.passage_batch import (
    PassageItem,
    judge_by_passage,
    passage_batching_enabled,
    split_group,
)
from busybee.verify.verify_entries import VerifyContext, verify_entries

from .helpers import judge_provider, make_chunk, make_entry

A = make_chunk("D1:p1:c0", "Net debt stood at Rs 40 crore. Revenue was Rs 900 crore.")
B = make_chunk("D1:p2:c0", "The board met four times. Revenue was Rs 900 crore.")


def tasks(provider: MockProvider) -> list[str]:
    return [call["task"] for call in provider.calls]


def listed(messages) -> list[tuple[str, str]]:  # noqa: ANN001
    body = messages[-1].content.split("\n\nStatements:\n", 1)[1]
    return [tuple(line.split(". ", 1)) for line in body.splitlines()]  # type: ignore[misc]


def ctx_for(provider: MockProvider, *chunks) -> VerifyContext:  # noqa: ANN002
    return VerifyContext(
        provider=provider, chunks_by_id={c.chunk_id: c for c in chunks}, store=None, embedder=None
    )


@pytest.fixture(autouse=True)
def passage_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_VERIFY_BATCH", "passage")


async def test_entries_citing_one_chunk_share_one_call() -> None:
    provider = judge_provider(supports=lambda s, p: "Net debt" in s)
    entries = [
        make_entry("E1", "Net debt is Rs 40 crore"),
        make_entry("E2", "Revenue is Rs 900 crore"),
        make_entry("E3", "Net debt was Rs 40 crore"),
    ]
    facts, dropped = await verify_entries(entries, ctx_for(provider, A), check_relevance=False)
    assert tasks(provider) == ["verify_entailment_passage"]
    assert [f.source_entry_id for f in facts] == ["E1", "E3"]
    assert [d.entry.entry_id for d in dropped] == ["E2"]
    assert facts[0].verification.method == "llm_entailment"


async def test_different_chunks_get_their_own_call() -> None:
    provider = judge_provider(supports=lambda s, p: True)
    entries = [
        make_entry("E1", "Net debt is Rs 40 crore"),
        make_entry("E2", "The board convened four times", "D1:p2:c0"),
    ]
    facts, _ = await verify_entries(entries, ctx_for(provider, A, B), check_relevance=False)
    assert tasks(provider) == ["verify_entailment_passage"] * 2
    assert len(facts) == 2


async def test_multi_chunk_entry_is_in_each_group_and_supported_by_any() -> None:
    provider = judge_provider(supports=lambda s, p: "Net debt" in p)
    entry = NotebookEntry(
        entry_id="E1",
        statement="Net debt is Rs 40 crore",
        citations=[Citation(chunk_id=c.chunk_id, doc_id="D1", page_no=c.page_no) for c in (A, B)],
    )
    facts, dropped = await verify_entries([entry], ctx_for(provider, A, B), check_relevance=False)
    assert not dropped
    assert tasks(provider) == ["verify_entailment_passage"] * 2
    assert [c.chunk_id for c in facts[0].citations] == [A.chunk_id]


def test_split_by_entry_cap_keeps_order() -> None:
    items = [PassageItem(f"k{i}", "short") for i in range(60)]
    groups = split_group(A, items)
    assert [len(g) for g in groups] == [25, 25, 10]
    assert [i.key for g in groups for i in g] == [i.key for i in items]


def test_split_by_token_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passage_batch, "MAX_GROUP_TOKENS", 600)
    items = [PassageItem(f"k{i}", "word " * 40) for i in range(6)]
    groups = split_group(A, items)
    assert len(groups) > 1 and all(len(g) >= 1 for g in groups)
    assert sum(len(g) for g in groups) == 6


async def test_missing_ids_are_retried_once_in_a_smaller_batch() -> None:
    seen: list[list[str]] = []

    def respond(messages, task):  # noqa: ANN001, ANN202
        rows = listed(messages)
        seen.append([text for _, text in rows])
        if len(seen) == 1:
            return json.dumps([{"id": "1", "v": "supported", "q": "Net debt stood at Rs 40"}])
        return json.dumps([{"id": n, "v": "unsupported"} for n, _ in rows])

    provider = MockProvider(respond)
    entries = {"E1": ("s one", [A]), "E2": ("s two", [A]), "E3": ("s three", [A])}
    out = await judge_by_passage(entries, provider)
    assert seen == [["s one", "s two", "s three"], ["s two", "s three"]]
    assert out[("E1", A.chunk_id)].verdict.value == "supported"
    assert out[("E2", A.chunk_id)].verdict.value == "unsupported"
    assert len(out) == 3


async def test_unusable_reply_retries_in_halves_then_falls_back_to_single_calls() -> None:
    def respond(messages, task):  # noqa: ANN001, ANN202
        if task == "verify_entailment_passage":
            return "garbled"
        return json.dumps({"v": "supported", "q": "Net debt stood at Rs 40"})

    provider = MockProvider(respond)
    entries = {f"E{i}": (f"statement {i}", [A]) for i in range(4)}
    out = await judge_by_passage(entries, provider)
    sizes = [len(listed(c["messages"])) for c in provider.calls if "passage" in c["task"]]
    assert sizes == [4, 2, 2]
    assert tasks(provider).count("verify_entailment") == 4
    assert all(v.verdict.value == "supported" for v in out.values()) and len(out) == 4


async def test_malformed_item_counts_as_missing() -> None:
    def respond(messages, task):  # noqa: ANN001, ANN202
        if task == "verify_entailment_passage":
            return json.dumps(
                [{"id": "1", "v": "maybe"}, {"id": "2", "v": "supported", "q": "Net debt stood"}]
            )
        return json.dumps({"v": "unsupported"})

    provider = MockProvider(respond)
    out = await judge_by_passage({"E1": ("a", [A]), "E2": ("b", [A])}, provider)
    assert out[("E1", A.chunk_id)].verdict.value == "unsupported"
    assert out[("E2", A.chunk_id)].verdict.value == "supported"


async def test_reply_that_raises_falls_back_to_per_entry_path() -> None:
    def respond(messages, task):  # noqa: ANN001, ANN202
        if task == "verify_entailment_passage":
            raise RuntimeError("boom")
        passage = messages[-1].content.split("Source passage:\n", 1)[1]
        return json.dumps({"v": "supported" if "Net debt" in passage else "unsupported", "q": ""})

    entry = make_entry("E1", "Net debt is Rs 40 crore")
    facts, dropped = await verify_entries(
        [entry], ctx_for(MockProvider(respond), A), check_relevance=False
    )
    assert len(facts) == 1 and not dropped


async def test_deterministic_checks_stay_in_front() -> None:
    provider = judge_provider()
    entries = [
        make_entry("E1", "Net debt stood at Rs 40 crore"),
        make_entry("E2", "Revenue was Rs 777 crore"),
    ]
    await verify_entries(entries, ctx_for(provider, A), check_relevance=False)
    assert tasks(provider) == []


async def test_entry_env_switch_uses_the_old_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_VERIFY_BATCH", "entry")
    assert not passage_batching_enabled()
    provider = judge_provider()
    entries = [make_entry("E1", "Revenue was Rs 900 crore"), make_entry("E2", "Net debt is Rs 40")]
    await verify_entries(entries, ctx_for(provider, A), check_relevance=False)
    assert set(tasks(provider)) <= {"verify_entailment"}
    assert "verify_entailment_passage" not in tasks(provider)


def test_default_is_passage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUSYBEE_VERIFY_BATCH")
    assert passage_batching_enabled()
    assert re.fullmatch(r"passage|entry", "passage")


async def test_prompt_shares_per_entry_definitions_and_partial_rule() -> None:
    from busybee.verify.entailment import _SYSTEM

    provider = judge_provider(supports=lambda s, p: True)
    await judge_by_passage({"E1": ("Net debt is Rs 40 crore", [A])}, provider)
    system = provider.calls[0]["messages"][0].content
    assert system.startswith(_SYSTEM)
    assert "only when part of the statement" in system
    assert "lakh/crore" in system and "rounding" in system and "template phrasing" in system
