"""Conflict detection: candidate pairs, the mock judge flow, resolution, and idempotent undo."""

import json
from decimal import Decimal

from busybee.llm import Message, MockProvider
from busybee.schema.documents import Document, DocumentKind
from busybee.schema.facts import (
    Citation,
    FactCategory,
    NumericValue,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.verify.conflicts import (
    BATCH_SIZE,
    detect_and_resolve_conflicts,
    find_conflict_candidates,
    is_conflicted,
    normalise_period,
    undo_conflicts_involving,
)


def number(label: str, value: str, period: str = "FY25", unit: str = "INR crore") -> NumericValue:
    return NumericValue(label=label, value=Decimal(value), unit=unit, period=period)


def fact(
    fact_id: str,
    statement: str,
    numbers: list[NumericValue],
    doc_id: str = "D1",
    category: FactCategory = FactCategory.revenue,
) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=category,
        citations=[Citation(chunk_id=f"{doc_id}:p1:c0", doc_id=doc_id, page_no=1)],
        numbers=numbers,
        verification=Verification(status=VerificationStatus.supported),
    )


def document(doc_id: str, kind: DocumentKind) -> Document:
    return Document(doc_id=doc_id, title=f"{kind.value} title", kind=kind)


DOCS = [document("D1", DocumentKind.financial_statements), document("D7", DocumentKind.news)]
F001 = fact(
    "F001",
    "Revenue from operations was INR 931.2 crore in FY25, up from INR 845.5 crore in FY24.",
    [number("revenue operations", "931.2"), number("value", "845.5", "FY24")],
)
F087 = fact(
    "F087",
    "Acme Textiles Limited closed FY25 with revenue of Rs 1,018 crore.",
    [number("revenue", "1018")],
    "D7",
)


PROMPTS: list[str] = []


def judge(conflict: bool = True) -> MockProvider:
    PROMPTS.clear()

    def respond(messages: list[Message], task: str) -> str:
        assert task == "verify_conflict"
        PROMPTS.append(messages[-1].content)
        count = messages[-1].content.count("Pair ")
        results = [
            {"id": n, "conflict": conflict, "metric": "revenue"} for n in range(1, count + 1)
        ]
        return json.dumps({"r": results}, separators=(",", ":"))

    return MockProvider(respond)


def test_period_normalisation() -> None:
    assert normalise_period("FY2024-25") == normalise_period("FY25") == "FY25"
    assert normalise_period("Q1 FY25") == "Q1 FY25"


def test_f001_f087_pair_is_a_candidate() -> None:
    [pair] = find_conflict_candidates([F001, F087])
    assert (pair.first_id, pair.second_id, pair.period) == ("F001", "F087", "FY25")
    assert pair.values == (Decimal("931.2"), Decimal("1018"))


def test_different_period_same_value_and_different_metric_are_not_pairs() -> None:
    other_year = fact(
        "F002", "Revenue was Rs 1,018 crore in FY24.", [number("revenue", "1018", "FY24")], "D7"
    )
    same_value = fact(
        "F003", "Revenue was Rs 931.2 crore in FY25.", [number("revenue", "931.2")], "D7"
    )
    near_value = fact("F004", "Revenue was Rs 935 crore in FY25.", [number("revenue", "935")], "D7")
    other_metric = fact("F005", "EBITDA was Rs 130 crore in FY25.", [number("ebitda", "130")], "D7")
    other_unit = fact(
        "F006", "Revenue was 12 percent in FY25.", [number("revenue", "12", unit="%")], "D7"
    )
    other_category = fact(
        "F007",
        "Revenue was Rs 1,018 crore in FY25.",
        [number("revenue", "1018")],
        "D7",
        FactCategory.news,
    )
    for other in (other_year, same_value, near_value, other_metric, other_unit, other_category):
        assert find_conflict_candidates([F001, other]) == []


def test_only_involving_limits_pairs_to_new_facts() -> None:
    assert find_conflict_candidates([F001, F087], only_involving={"F001"}) != []
    assert find_conflict_candidates([F001, F087], only_involving={"F999"}) == []


async def test_judge_flow_and_resolution_by_source_priority() -> None:
    outcome = await detect_and_resolve_conflicts([F001, F087], DOCS, judge())
    kept, lost = outcome.facts
    assert outcome.candidate_count == 1
    assert [(n.fact_id, n.resolved_by) for n in kept.conflicts] == [("F087", "source_priority")]
    assert not is_conflicted(kept)
    assert is_conflicted(lost) and lost.conflicts == []
    assert lost.verification is not None and "F001" in lost.verification.notes
    [concern] = outcome.concerns
    assert concern.concern_id == "CF001" and concern.found is False
    assert concern.fact_ids == ["F001", "F087"]
    prompt = PROMPTS[0]
    assert "news title" in prompt and "financial_statements" in prompt


async def test_higher_authority_wins_regardless_of_order() -> None:
    outcome = await detect_and_resolve_conflicts([F087, F001], DOCS, judge())
    assert [is_conflicted(f) for f in outcome.facts] == [True, False]


async def test_judge_says_no_conflict_changes_nothing() -> None:
    outcome = await detect_and_resolve_conflicts([F001, F087], DOCS, judge(False))
    assert outcome.facts == [F001, F087] and outcome.concerns == []


async def test_equal_authority_is_left_unresolved_and_both_stay_live() -> None:
    docs = [document("D1", DocumentKind.news), document("D7", DocumentKind.news)]
    outcome = await detect_and_resolve_conflicts([F001, F087], docs, judge())
    assert not any(is_conflicted(f) for f in outcome.facts)
    assert {n.resolved_by for f in outcome.facts for n in f.conflicts} == {"unresolved"}
    assert len(outcome.concerns) == 1


async def test_unusable_judge_reply_yields_no_conflict() -> None:
    outcome = await detect_and_resolve_conflicts([F001, F087], DOCS, MockProvider("nonsense"))
    assert outcome.concerns == [] and not any(is_conflicted(f) for f in outcome.facts)


async def test_pairs_are_batched() -> None:
    many = [
        fact(
            f"F{100 + n}",
            f"Revenue was Rs {2000 + 100 * n} crore in FY25.",
            [number("revenue", str(2000 + 100 * n))],
            "D7",
        )
        for n in range(6)
    ]
    await detect_and_resolve_conflicts([F001, *many], DOCS, judge())
    sizes = [prompt.count("Pair ") for prompt in PROMPTS]
    assert max(sizes) <= BATCH_SIZE and len(sizes) > 1


async def test_undo_restores_loser_and_drops_stale_concern() -> None:
    outcome = await detect_and_resolve_conflicts([F001, F087], DOCS, judge())
    facts, concerns = undo_conflicts_involving(outcome.facts[1:], outcome.concerns, {"F001"})
    assert not any(is_conflicted(f) for f in facts) and concerns == []
    assert facts[0].verification is not None
    assert facts[0].verification.status is VerificationStatus.supported


async def test_note_is_built_by_code_from_the_two_statements() -> None:
    outcome = await detect_and_resolve_conflicts([F001, F087], DOCS, judge())
    kept, _ = outcome.facts
    [note] = kept.conflicts
    assert F001.statement in note.note and F087.statement in note.note
    assert "F001" in note.note and "F087" in note.note
    [concern] = outcome.concerns
    assert F001.statement in concern.reasoning


async def test_judge_prompt_asks_for_compact_reply_without_note() -> None:
    provider = judge()
    await detect_and_resolve_conflicts([F001, F087], DOCS, provider)
    system = provider.calls[0]["messages"][0].content
    assert '{"r":[{"id":' in system and "minified" in system
    assert "'note'" not in system
