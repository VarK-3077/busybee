"""Derived-slot components: Indoco v6 net debt regression, missing/proxy cautions, one basis."""

import json
from decimal import Decimal
from pathlib import Path

from policy_helpers import BANKS_DIR

from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import bind_inputs
from busybee.policy.rules import ResolvedRule, build_rule_results
from busybee.schema.facts import FactScope, NumericValue, VerifiedFact
from busybee.schema.policy import BoundInput, RuleStatus, ScoreSpec

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_net_debt_facts.json"
LAKH = "INR lakh"


def _facts() -> list[VerifiedFact]:
    return [VerifiedFact.model_validate(item) for item in json.loads(FIXTURE.read_text())]


def _fss_only() -> list[ScoreSpec]:
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id.startswith("fin"))
    keep = {"net_debt", "ebitda"}
    return [spec.model_copy(update={"inputs": [i for i in spec.inputs if i.slot in keep]})]


def _term(fact_id: str, value: str, component: str, sign: int) -> dict:
    return {
        "fact_id": fact_id,
        "value": value,
        "unit": LAKH,
        "sign": sign,
        "component": component,
    }


def _reply(terms: list[dict], missing: list[str]) -> str:
    ebitda = {
        "score_id": "financial_strength_score",
        "slot": "ebitda",
        "fact_id": "F164",
        "value": "15716.21",
        "unit": LAKH,
    }
    net_debt = {
        "score_id": "financial_strength_score",
        "slot": "net_debt",
        "terms": terms,
        "missing": missing,
    }
    return json.dumps({"bindings": [net_debt, ebitda]})


BORROWINGS = _term("F174", "70560.64", "total borrowings", 1)
LEASES = _term("F152", "5389.61", "lease liabilities", 1)
CASH = _term("F099", "1293.72", "cash and bank balances", -1)
BANK = _term("F091", "706.12", "cash and bank balances", -1)
NON_CURRENT = _term("F087", "15974.92", "liquid investments", -1)


async def test_indoco_net_debt_rejects_non_current_investments_and_the_rule_fails() -> None:
    wrong = _reply([BORROWINGS, LEASES, CASH, BANK, NON_CURRENT], [])
    right = _reply([BORROWINGS, LEASES, CASH, BANK], ["liquid investments"])
    provider = MockProvider({"policy.bind_inputs": [wrong, right]})
    result = await bind_inputs(provider, _fss_only(), _facts())
    assert len(provider.calls) == 2
    retry = provider.calls[1]["messages"][-1].content
    assert "F087 is under non-current assets" in retry
    prompt = provider.calls[0]["messages"][-1].content
    assert "component 'liquid investments': current investments only" in prompt
    bound = {item.slot: item for item in result.bound["financial_strength_score"]}
    net_debt, ebitda = bound["net_debt"], bound["ebitda"]
    assert net_debt.value == Decimal("739.51") and net_debt.value_scaled == 73951
    assert "F087" not in net_debt.derived_from
    assert "liquid investments" in net_debt.caution
    ratio = Decimal(net_debt.value_scaled) / Decimal(ebitda.value_scaled)
    assert round(ratio, 2) == Decimal("4.71")
    assert 2 * net_debt.value_scaled > 9 * ebitda.value_scaled

    rule = next(r for r in load_bank(BANKS_DIR, "demo_bank").rules if "net_debt" in r.rule_id)
    resolved = {rule.rule_id: ResolvedRule(inputs=[net_debt, ebitda])}
    [out] = build_rule_results([rule], resolved, {rule.rule_id: "fail"}, None, [])
    assert out.status is RuleStatus.fail
    assert (out.measure, out.computed_value, out.threshold) == (
        "Net debt / EBITDA",
        "4.71x",
        "at most 4.5x",
    )


async def test_all_components_listed_but_one_missing_makes_a_passing_rule_caution() -> None:
    reply = _reply([BORROWINGS, LEASES, CASH, BANK], ["liquid investments"])
    provider = MockProvider({"policy.bind_inputs": [reply]})
    result = await bind_inputs(provider, _fss_only(), _facts())
    net_debt = next(i for i in result.bound["financial_strength_score"] if i.slot == "net_debt")
    rule = next(r for r in load_bank(BANKS_DIR, "demo_bank").rules if "net_debt" in r.rule_id)
    resolved = {rule.rule_id: ResolvedRule(inputs=[net_debt])}
    [out] = build_rule_results([rule], resolved, {rule.rule_id: "pass"}, None, [])
    assert out.status is RuleStatus.caution
    assert "liquid investments" in out.caution_reason
    assert "missing component" in out.inputs[0].note


async def test_a_component_neither_used_nor_declared_missing_is_rejected() -> None:
    incomplete = _reply([BORROWINGS, LEASES, CASH, BANK], [])
    provider = MockProvider({"policy.bind_inputs": [incomplete, incomplete]})
    result = await bind_inputs(provider, _fss_only(), _facts())
    assert any("liquid investments" in line for line in result.rejected)
    assert all(i.slot != "net_debt" for i in result.bound["financial_strength_score"])


def test_a_proxy_note_makes_a_passing_rule_caution() -> None:
    proxy = BoundInput(
        slot="cfads", fact_id="F1", value=Decimal(1), caution="proxy used: tax charge"
    )
    rule = next(r for r in load_bank(BANKS_DIR, "demo_bank").rules if r.rule_id == "dscr_min")
    resolved = {rule.rule_id: ResolvedRule(inputs=[proxy])}
    [out] = build_rule_results([rule], resolved, {rule.rule_id: "pass"}, None, [])
    assert out.status is RuleStatus.caution and "tax charge" in out.caution_reason


def _scoped(fact_id: str, scope: FactScope, value: str) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=f"{fact_id} figure was INR {value} crore",
        scope=scope,
        numbers=[NumericValue(label="n", value=Decimal(value), unit="INR crore")],
    )


def test_mixed_bases_in_one_rule_make_it_caution_with_the_reason() -> None:
    facts = {
        "F1": _scoped("F1", FactScope.consolidated, "10"),
        "F2": _scoped("F2", FactScope.standalone, "5"),
    }
    inputs = [
        BoundInput(slot="net_debt", fact_id="F1", value=Decimal(10), value_scaled=1000),
        BoundInput(slot="ebitda", fact_id="F2", value=Decimal(5), value_scaled=500),
    ]
    rule = next(r for r in load_bank(BANKS_DIR, "demo_bank").rules if "net_debt" in r.rule_id)
    resolved = {rule.rule_id: ResolvedRule(inputs=inputs)}
    [out] = build_rule_results([rule], resolved, {rule.rule_id: "pass"}, None, [], facts)
    assert out.status is RuleStatus.caution
    assert "mix bases" in out.caution_reason and "F1" in out.inputs[0].note


async def test_binding_keeps_to_the_consolidated_basis_when_statements_exist() -> None:
    consolidated = [_scoped(f"C{n}", FactScope.consolidated, "9") for n in range(5)]
    stray = _scoped("S1", FactScope.standalone, "7")
    stray = stray.model_copy(update={"statement": "Standalone EBITDA was INR 7 crore"})
    own = consolidated[0].model_copy(update={"statement": "Consolidated EBITDA was INR 9 crore"})
    wrong = {
        "score_id": "financial_strength_score",
        "slot": "ebitda",
        "fact_id": "S1",
        "value": "7",
        "unit": "INR crore",
    }
    right = {**wrong, "fact_id": "C0", "value": "9"}
    replies = [
        json.dumps({"bindings": [wrong]}),
        json.dumps({"bindings": []}),
        json.dumps({"bindings": [right]}),
    ]
    provider = MockProvider({"policy.bind_inputs": replies})
    facts = [own, *consolidated[1:], stray]
    result = await bind_inputs(provider, _fss_only(), facts)
    assert result.basis is FactScope.consolidated
    assert "S1 is standalone but this run uses consolidated" in (
        provider.calls[2]["messages"][-1].content
    )
    ebitda = [i for i in result.bound["financial_strength_score"] if i.slot == "ebitda"]
    assert [i.fact_id for i in ebitda] == ["C0"]
