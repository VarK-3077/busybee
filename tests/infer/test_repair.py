"""Check the Lean repair loop: repaired claims pass, false ones drop, unit errors stay unchecked."""

import json
from decimal import Decimal

import pytest

from busybee.infer import prompts
from busybee.infer.independent_check import TASK as CHECK_TASK
from busybee.infer.repair import TASK as REPAIR_TASK
from busybee.infer.run_infer import run_infer
from busybee.lean.toolchain import find_lake, find_lean
from busybee.llm import MockProvider
from busybee.schema.facts import Citation, FactCategory, NumericValue, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.report import Inference

pytestmark = pytest.mark.skipif(
    find_lean() is None or find_lake() is None,
    reason="Lean toolchain is not installed",
)


def _fact(fact_id: str, statement: str, value: str, unit: str) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=FactCategory.other,
        citations=[Citation(chunk_id="D1:p1:c1", doc_id="D1", page_no=1)],
        numbers=[NumericValue(label="n", value=Decimal(value), unit=unit)],
    )


FACTS = [
    _fact("F001", "Interest coverage was 0.9x.", "0.9", "x"),
    _fact("F002", "EBITDA INR 18,679 lakh.", "18679", "INR lakh"),
    _fact("F003", "Finance cost INR 88.5 crore.", "88.5", "INR crore"),
]


def _draft(claim: dict) -> str:
    inference = {
        "opinion": "Interest cover is thin.",
        "fact_ids": ["F001", "F002", "F003"],
        "reasoning": "F001 is below one.",
        "confidence": 0.7,
        "quantitative": True,
        "lean_claim": claim,
    }
    return json.dumps({"inferences": [inference]})


def _claim(expression: str) -> dict:
    return {
        "facts": {"coverage": "F001", "ebitda": "F002", "finance_cost": "F003"},
        "claim": expression,
    }


def _repair(quantitative: bool, claim: dict | None, opinion: str = "") -> str:
    return json.dumps({"quantitative": quantitative, "lean_claim": claim, "opinion": opinion})


async def _run(tmp_path, infer_reply: str, repairs: list[str]):
    write_models_atomic(tmp_path / "verified_facts.json", FACTS)
    provider = MockProvider(
        {
            prompts.TASK: [infer_reply],
            REPAIR_TASK: repairs,
            CHECK_TASK: [json.dumps({"ok": True, "problems": []})],
        }
    )
    result = await run_infer(tmp_path, {"run_id": "r"}, provider)
    return result, provider


def _repair_calls(provider: MockProvider) -> list:
    return [call for call in provider.calls if call["task"] == REPAIR_TASK]


async def test_true_ratio_claim_from_logged_style_units_passes_without_repair(tmp_path) -> None:
    result, provider = await _run(tmp_path, _draft(_claim("coverage < 1")), [])
    assert result[0].lean is not None and result[0].lean.compile.ok
    assert _repair_calls(provider) == []


async def test_false_claim_fails_lean(tmp_path) -> None:
    result, _ = await _run(
        tmp_path,
        _draft(_claim("100 * ebitda < 100 * finance_cost")),
        [_repair(True, _claim("100 * ebitda < 100 * finance_cost"))] * 2,
    )
    assert result == []


async def test_first_reply_fails_repaired_reply_passes(tmp_path) -> None:
    bad = _claim("coverage < ebitda")
    good = _claim("100 * finance_cost < 100 * ebitda")
    result, provider = await _run(tmp_path, _draft(bad), [_repair(True, good)])
    assert len(result) == 1
    assert result[0].lean is not None and result[0].lean.compile.ok
    calls = _repair_calls(provider)
    assert len(calls) == 1
    prompt = calls[0]["messages"][-1].content
    assert "incompatible units" in prompt and "F002" in prompt and "coverage < ebitda" in prompt


async def test_exhausted_retries_with_false_claim_drops_inference(tmp_path) -> None:
    false_claim = _claim("100 * ebitda < 100 * finance_cost")
    result, provider = await _run(tmp_path, _draft(false_claim), [_repair(True, false_claim)])
    assert result == []
    assert len(_repair_calls(provider)) == 2
    dropped = read_models(tmp_path / "inferences_dropped.json", Inference)
    assert len(dropped) == 1 and "Dropped from the report" in dropped[0].reasoning
    assert read_models(tmp_path / "inferences.json", Inference) == []


async def test_exhausted_retries_with_unit_error_stays_unchecked(tmp_path) -> None:
    bad = _claim("coverage < ebitda")
    result, provider = await _run(tmp_path, _draft(bad), [_repair(True, bad)])
    assert len(result) == 1 and result[0].quantitative and result[0].lean is None
    assert "unchecked" in result[0].reasoning
    assert len(_repair_calls(provider)) == 2


async def test_model_may_withdraw_the_claim(tmp_path) -> None:
    result, _ = await _run(tmp_path, _draft(_claim("coverage < ebitda")), [_repair(False, None)])
    assert len(result) == 1 and not result[0].quantitative and result[0].lean is None
