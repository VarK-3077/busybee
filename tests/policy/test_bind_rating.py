"""Rating grades are mapped to the bank index by table lookup, not by the model."""

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import bind_inputs
from busybee.policy.bind_rating import grades_in, rating_binding
from busybee.schema.facts import VerifiedFact


def _slot():
    bank = load_bank(BANKS_DIR, "demo_bank")
    irg = next(s for s in bank.scores if s.score_id == "internal_risk_grade")
    return bank, next(s for s in irg.inputs if s.slot == "external_rating_index")


def _facts(*statements: str) -> list[VerifiedFact]:
    return [VerifiedFact(fact_id=f"F{n:03d}", statement=s) for n, s in enumerate(statements, 1)]


def test_policy_table_is_the_one_in_the_policy_text() -> None:
    _, slot = _slot()
    assert slot.mapping["AAA"] == 1 and slot.mapping["A"] == 6 and slot.mapping["BBB-"] == 10
    assert slot.mapping["BB+"] == 11 and slot.mapping["C"] == 17 and slot.mapping["D"] == 22


def test_downgrade_chain_ends_on_the_latest_grade_and_ignores_short_term() -> None:
    _, slot = _slot()
    facts = _facts(
        "The long-term rating was downgraded from [ICRA]AA- (Stable) in May 2024 to "
        "[ICRA]A+ (Negative) in July 2025, and further to [ICRA]A (Negative) in August 2025.",
        "The short-term rating was downgraded from [ICRA]A1+ to [ICRA]A2+ in August 2025.",
        "A downgrade may follow if margins stay weak; Plant C is idle.",
    )
    bound = rating_binding(slot, facts)
    assert bound is not None
    assert (bound.fact_id, bound.value_scaled) == ("F001", 6)
    assert "A maps to index 6" in bound.note


def test_latest_dated_fact_wins_and_other_grades_are_noted() -> None:
    _, slot = _slot()
    facts = _facts(
        "ICRA assigned the company a long-term rating of 'AA-' (Stable) in March 2024.",
        "ICRA downgraded the long-term credit rating from 'A+' (Negative) to 'A' (Negative) "
        "effective August 04, 2025.",
    )
    bound = rating_binding(slot, facts)
    assert bound is not None and bound.fact_id == "F002" and bound.value_scaled == 6
    assert "AA-" in bound.note


def test_prose_without_a_rating_context_never_matches() -> None:
    _, slot = _slot()
    grades = list(slot.mapping)
    assert grades_in("The company is rated by CRISIL at BBB+ (Stable).", grades) == ["BBB+"]
    assert grades_in("Revenue is class A (Negative) in the note", grades) == []
    assert grades_in("ICRA rating A1+ for commercial paper", grades) == []
    assert rating_binding(slot, _facts("Net worth was 100 crore")) is None


async def test_binder_uses_the_table_and_makes_no_model_call_for_a_stated_grade() -> None:
    from busybee.llm import MockProvider

    bank, _ = _slot()
    facts = _facts("CRISIL reaffirmed the long-term rating at BBB- (Stable).")
    provider = MockProvider({"policy.bind_inputs": ['{"bindings": []}'] * 2})
    result = await bind_inputs(provider, bank.scores, facts)
    rating = next(
        i for i in result.bound["internal_risk_grade"] if i.slot == "external_rating_index"
    )
    assert rating.value_scaled == 10 and rating.fact_id == "F001"
    assert all(call["task"] != "policy.judge_slot" for call in provider.calls)
    assert ("internal_risk_grade", "major_red_flag_count") in result.unbound
