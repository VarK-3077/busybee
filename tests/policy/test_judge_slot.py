"""Judged slots: one model call with the policy rubric, accepted only with valid cited facts."""

import json

from policy_helpers import BANKS_DIR

from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import bind_inputs
from busybee.policy.judge_slot import judge_candidates
from busybee.policy.policy_sections import split_policy_sections
from busybee.schema.facts import VerifiedFact


def _facts(*statements: str) -> list[VerifiedFact]:
    return [VerifiedFact(fact_id=f"F{n:03d}", statement=s) for n, s in enumerate(statements, 1)]


def _reply(value, ids, text="because"):
    return json.dumps({"value": value, "fact_ids": ids, "justification": text})


async def _run(facts, replies):
    bank = load_bank(BANKS_DIR, "demo_bank")
    empty = json.dumps({"bindings": []})
    provider = MockProvider({"policy.judge_slot": replies, "policy.bind_inputs": [empty] * 2})
    result = await bind_inputs(provider, bank.scores, facts, split_policy_sections(bank.policy_md))
    bound = {i.slot: i for i in result.bound["internal_risk_grade"]}
    return provider, result, bound


FACTS = (
    "The Statutory Auditor's report contains a qualification on trade receivables.",
    "The company has not been declared a wilful defaulter by any bank.",
    "USFDA issued a warning letter to Goa Plant II after Form 483 observations.",
    "Revenue rose 10 percent.",
)


async def test_flag_and_count_are_judged_with_rubric_facts_and_note() -> None:
    provider, result, bound = await _run(
        list(_facts(*FACTS)),
        [
            _reply(2, ["F001", "F003"], "audit qualification and FDA warning letter"),
            _reply(0, ["F002"], "no wilful default declared"),
        ],
    )
    count, flag = bound["major_red_flag_count"], bound["default_flag"]
    assert (count.value_scaled, count.fact_id, count.derived_from) == (2, "F001", ["F001", "F003"])
    assert count.note == "audit qualification and FDA warning letter"
    assert (flag.value_scaled, flag.fact_id, flag.note) == (0, "F002", "no wilful default declared")
    judge_calls = [c for c in provider.calls if c["task"] == "policy.judge_slot"]
    assert len(judge_calls) == 2
    prompt = judge_calls[0]["messages"][-1].content
    assert "Each of the following is a **major red flag**" in prompt
    assert "F004" not in prompt and "F003: USFDA" in prompt


async def test_answer_citing_unknown_fact_or_bad_value_is_rejected() -> None:
    _, result, bound = await _run(list(_facts(*FACTS)), [_reply(1, ["F999"]), _reply(7, ["F002"])])
    assert "major_red_flag_count" not in bound and "default_flag" not in bound
    reasons = result.unbound
    assert "cited no valid fact" in reasons[("internal_risk_grade", "major_red_flag_count")]
    assert "must be 0 or 1" in reasons[("internal_risk_grade", "default_flag")]


async def test_slot_without_candidate_facts_is_not_asked() -> None:
    provider, result, _ = await _run(list(_facts("Revenue rose 10 percent.")), [])
    assert [c for c in provider.calls if c["task"] == "policy.judge_slot"] == []
    assert "cannot evidence" in result.unbound[("internal_risk_grade", "default_flag")]


async def test_rating_falls_back_to_the_model_only_when_no_fact_states_a_grade() -> None:
    facts = _facts("The lenders' rating committee met in June.", "No wilful default was declared.")
    _, result, bound = await _run(
        list(facts),
        [
            _reply("BBB+", ["F001"], "named in the rating note"),
            _reply(0, ["F002"]),
            _reply(0, ["F002"]),
        ],
    )
    assert "external_rating_index" not in bound
    assert (
        "does not appear in the cited facts"
        in result.unbound[("internal_risk_grade", "external_rating_index")]
    )


def test_candidates_are_ranked_by_distinct_keyword_hits() -> None:
    facts = _facts("A default and a wilful default", "wilful default and NPA", "NPA only", "none")
    ranked = judge_candidates(["default", "wilful", "NPA"], facts)
    assert [f.fact_id for f in ranked] == ["F002", "F001", "F003"]


async def test_count_slot_defaults_to_zero_when_the_model_gives_no_usable_value() -> None:
    for replies in (
        [json.dumps({"fact_ids": ["F001"], "justification": "rambling"})],
        [_reply(99, ["F001"])],
        ["not json at all"] * 3,
    ):
        _, result, bound = await _run(list(_facts(*FACTS)), [*replies, _reply(0, ["F002"])])
        count = bound["major_red_flag_count"]
        assert count.value_scaled == 0
        assert count.note.startswith("judged_default: true; no qualifying red flag found among 3")
        assert sorted(count.derived_from) == ["F001", "F002", "F003"]
        assert ("internal_risk_grade", "major_red_flag_count") not in result.unbound


async def test_default_flag_never_defaults_and_counts_without_candidates_stay_unbound() -> None:
    facts = list(_facts(*FACTS))
    _, result, bound = await _run(facts, [_reply(1, ["F001"]), *["not json at all"] * 3])
    assert "default_flag" not in bound
    assert ("internal_risk_grade", "default_flag") in result.unbound
    _, result, bound = await _run(list(_facts("Revenue rose 10 percent.")), [])
    assert "major_red_flag_count" not in bound
