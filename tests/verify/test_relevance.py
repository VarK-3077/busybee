"""Relevance judging is batched at 40 entries and records a reason for every decision."""

import json

from busybee.llm import MockProvider
from busybee.verify.relevance import batches_of, judge_relevance

from .helpers import make_entry


def test_batches_of_splits_at_size() -> None:
    assert [len(b) for b in batches_of(list(range(45)), 40)] == [40, 5]


async def test_judge_relevance_uses_one_call_per_batch() -> None:
    entries = [make_entry(f"E{i:03d}", f"Fact {i}") for i in range(45)]
    seen: list[int] = []

    def respond(messages, task):  # noqa: ANN001, ANN202
        listed = [line for line in messages[-1].content.splitlines() if line.startswith("- E")]
        seen.append(len(listed))
        ids = [line.split()[1] for line in listed]
        return json.dumps({"drop": [[i, "trivia"] for i in ids if i == "E003"]})

    provider = MockProvider(respond)
    decisions = await judge_relevance(entries, "ctx", provider)
    assert sorted(seen) == [5, 40]
    assert all(call["task"] == "verify_relevance" for call in provider.calls)
    assert len(decisions) == 45
    assert not decisions["E003"].keep
    assert decisions["E004"].keep
    assert decisions["E003"].reason == "immaterial detail"
    assert decisions["E004"].reason == "kept"


async def test_missing_decision_defaults_to_keep() -> None:
    provider = MockProvider(json.dumps({"drop": []}))
    decisions = await judge_relevance([make_entry("E1", "Fact")], "", provider)
    assert decisions["E1"].keep and decisions["E1"].reason == "kept"


async def test_reason_codes_are_expanded_and_unknown_ids_are_ignored() -> None:
    reply = {"drop": [["E1", "dup"], ["E2", "admin"], ["E3", "weird"], ["E9", "stale"], ["E4"]]}
    provider = MockProvider(json.dumps(reply, separators=(",", ":")))
    entries = [make_entry(f"E{i}", f"Fact {i}") for i in range(1, 6)]
    decisions = await judge_relevance(entries, "", provider)
    assert [decisions[f"E{i}"].keep for i in range(1, 6)] == [False, False, False, False, True]
    assert decisions["E1"].reason == "duplicate of another entry"
    assert decisions["E2"].reason == "corporate or administrative boilerplate"
    assert decisions["E3"].reason == "weird"
    assert "E9" not in decisions
    assert decisions["E4"].reason == "dropped by relevance filter"


def test_prompt_asks_for_minified_drop_list_with_reason_codes() -> None:
    from busybee.verify.relevance import DROP_REASONS, build_relevance_messages

    system = build_relevance_messages([make_entry("E1", "Fact")], "ctx")[0].content
    assert '{"drop":[["E012","dup"]' in system and "minified" in system
    assert all(code in system for code in DROP_REASONS)
    assert set(DROP_REASONS) == {"dup", "trivia", "admin", "offtopic", "stale"}


def test_required_inputs_are_shown_to_the_relevance_filter() -> None:
    from busybee.verify.relevance import build_relevance_messages

    entry = make_entry("E1", "Fact")
    plain = build_relevance_messages([entry], "ctx")[0].content
    guarded = build_relevance_messages([entry], "ctx", "- current_assets: Total current assets")[
        0
    ].content
    assert "current_assets" not in plain
    assert "Always keep an entry" in guarded and "current_assets" in guarded
    assert "a repeat in a different document is a second citation" in plain


def _big_notebook(count: int = 900):  # noqa: ANN202
    from busybee.schema.facts import FactCategory

    entries = []
    for i in range(count):
        entry = make_entry(
            f"E{i:04d}",
            f"Fact number {i} about topic{i % 30} revenue growth and margin trends " * 2,
            chunk_id=f"D{i % 9}:p1:c0",
        )
        entry.doc_id = f"D{i % 9}"
        entry.importance = 1 + i % 5
        entry.category = FactCategory.revenue
        entries.append(entry)
    return entries


def test_batch_context_stays_under_the_cap_on_a_900_entry_notebook() -> None:
    from busybee.llm import count_tokens
    from busybee.verify.relevance import build_batch_context, document_summary_lines

    notebook = _big_notebook()
    titles = {f"D{i}": f"Doc {i}" for i in range(9)}
    summary = document_summary_lines(notebook, titles, {})
    assert len(summary) == 9 and "revenue=100" in summary[0]
    context = build_batch_context(notebook[:40], notebook, summary, 6000)
    assert count_tokens(context) <= 6000
    assert context.startswith("D0 | Doc 0")
    assert count_tokens(context) < count_tokens("\n".join(map(str, notebook)))


def test_same_document_entries_are_preferred_when_over_the_cap() -> None:
    from busybee.schema.facts import FactCategory
    from busybee.verify.relevance import build_batch_context

    batch = [make_entry("B1", "alpha beta gamma delta", chunk_id="D1:p1:c0")]
    batch[0].doc_id = "D1"
    same = make_entry("S1", "unrelated words only", chunk_id="D1:p1:c0")
    same.doc_id = "D1"
    other = make_entry("O1", "alpha beta shared tokens", chunk_id="D2:p1:c0")
    other.doc_id = "D2"
    unrelated = make_entry("U1", "nothing in common", chunk_id="D3:p1:c0")
    unrelated.doc_id = "D3"
    for entry in (same, other, unrelated):
        entry.category = FactCategory.other
    notebook = [*batch, same, other, unrelated]
    roomy = build_batch_context(batch, notebook, [], 1000)
    assert "S1" in roomy and "O1" in roomy and "U1" not in roomy
    from busybee.extract.condensed import condense_entry
    from busybee.llm import count_tokens

    tight = count_tokens(condense_entry(same)) + 10
    squeezed = build_batch_context(batch, notebook, [], tight)
    assert "S1" in squeezed and "O1" not in squeezed


async def test_judge_relevance_sends_per_batch_context(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("BUSYBEE_RELEVANCE_CONTEXT_TOKENS", "500")
    notebook = _big_notebook(120)
    provider = MockProvider(json.dumps({"drop": []}))
    await judge_relevance(notebook, "", provider, notebook=notebook, summary_lines=["D0 | x"])
    from busybee.llm import count_tokens

    assert len(provider.calls) == 3
    for call in provider.calls:
        shown = call["messages"][-1].content.split("Decide on exactly")[0]
        assert count_tokens(shown) < 600
