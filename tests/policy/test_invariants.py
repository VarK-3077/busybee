"""Invariant parser/evaluator, violation warnings with one binder retry, and the clean case."""

import json

import pytest
from policy_helpers import BANKS_DIR, binding_json, example_facts

from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import bind_inputs
from busybee.policy.invariants import (
    InvariantError,
    check_invariants,
    enforce_invariants,
    evaluate_expression,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a <= b", True),
        ("a + b * 2 == 7", True),
        ("(a + b) * 2 == 8", True),
        ("a - b - 1 < 0", True),
        ("-a < 0", True),
        ("a != b", True),
        ("a > b", False),
        ("a * 1.5 >= 2", False),
    ],
)
def test_evaluate(text: str, expected: bool) -> None:
    assert evaluate_expression(text, {"a": 1, "b": 3}) is expected


@pytest.mark.parametrize("text", ["a", "a < ", "a < b < c", "a ** b < 1", "__import__('os') < 1"])
def test_parser_rejects_bad_expressions(text: str) -> None:
    with pytest.raises(InvariantError):
        evaluate_expression(text, {"a": 1, "b": 2})


def _bank():
    return load_bank(BANKS_DIR, "demo_bank")


def _bad_facts():
    facts = example_facts()
    for fact in facts:
        if fact.numbers[0].label == "Net debt":
            fact.numbers[0].value = type(fact.numbers[0].value)("1800.00")
            fact.statement = "Net debt was 1800.00 INR crore"
    return facts


async def _bound(facts, provider):
    bank = _bank()
    return bank, (await bind_inputs(provider, bank.scores, facts)).bound


async def test_satisfied_invariants_give_no_warning_and_no_retry() -> None:
    facts = example_facts()
    provider = MockProvider({"policy.bind_inputs": [binding_json(facts)]})
    bank, bound = await _bound(facts, provider)
    assert bank.invariants
    assert check_invariants(bank.invariants, bound) == []
    calls = len(provider.calls)
    _, warnings = await enforce_invariants(provider, bank.scores, bank.invariants, facts, bound)
    assert warnings == {}
    assert len(provider.calls) == calls


async def test_violation_warns_after_exactly_one_retry() -> None:
    facts = _bad_facts()
    provider = MockProvider({"policy.bind_inputs": [binding_json(facts)]})
    bank, bound = await _bound(facts, provider)
    calls = len(provider.calls)
    _, warnings = await enforce_invariants(provider, bank.scores, bank.invariants, facts, bound)
    assert len(provider.calls) == calls + 1
    retry_prompt = provider.calls[-1]["messages"][-1].content
    assert "Net debt cannot exceed total debt" in retry_prompt
    text = " ".join(warnings["financial_strength_score"])
    assert "Net debt cannot exceed total debt" in text
    assert "F001" in text
    assert "F006" in text


async def test_retry_that_fixes_the_binding_clears_the_warning() -> None:
    bad, good = _bad_facts(), example_facts()
    fixed = json.loads(binding_json(good))
    provider = MockProvider({"policy.bind_inputs": [binding_json(bad), json.dumps(fixed)]})
    bank, bound = await _bound(bad, provider)
    bound, warnings = await enforce_invariants(provider, bank.scores, bank.invariants, good, bound)
    assert warnings == {}
    assert check_invariants(bank.invariants, bound) == []
