"""Indoco v8 regression: derived slots are rebound after slot search, with principal in DSCR.

In v8 net debt was bound from total borrowings alone before the slot search recovered current
lease liabilities, cash and bank balances, and debt service was an interest-expense proxy with no
principal repayment. The fixture holds those facts as the fixed slot search writes them (figure
with its header unit). `complete_derived_slots` must rebuild both on the consolidated basis.
"""

import json
from decimal import Decimal
from pathlib import Path

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingResult
from busybee.policy.complete_derived import complete_derived_slots
from busybee.policy.slot_search import build_queries, search_targets
from busybee.schema.facts import FactScope, VerifiedFact
from busybee.schema.policy import BoundInput, ScoreSpec
from busybee.verify.numbers import numeric_values_from

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_v8_rebind_facts.json"
FSS = "financial_strength_score"
NET_DEBT_CAUTION = (
    "missing component(s): lease liabilities, cash and bank balances, liquid investments; "
    "value computed without them"
)
PROXY = (
    "missing component(s): scheduled principal repayments; value computed without them; "
    "proxy used: Interest Expense is an accrual-based P&L figure, used as a proxy for cash "
    "interest paid"
)


def _facts(skip: set[str] | None = None) -> list[VerifiedFact]:
    items = json.loads(FIXTURE.read_text())
    return [
        VerifiedFact.model_validate({**item, "numbers": numeric_values_from(item["statement"])})
        for item in items
        if item["fact_id"] not in (skip or set())
    ]


def _spec() -> list[ScoreSpec]:
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)
    keep = {"net_debt", "debt_service"}
    return [spec.model_copy(update={"inputs": [i for i in spec.inputs if i.slot in keep]})]


def _v8_binding() -> BindingResult:
    net_debt = BoundInput(
        slot="net_debt",
        fact_id="F124",
        value=Decimal("1035.84"),
        unit="INR crore x 100",
        value_scaled=103584,
        derived_from=["F124"],
        caution=NET_DEBT_CAUTION,
        missing=["lease liabilities", "cash and bank balances", "liquid investments"],
    )
    debt_service = BoundInput(
        slot="debt_service",
        fact_id="F109",
        value=Decimal("80.27"),
        unit="INR crore x 100",
        value_scaled=8027,
        derived_from=["F109"],
        caution=PROXY,
        missing=["scheduled principal repayments"],
    )
    return BindingResult(bound={FSS: [net_debt, debt_service]}, basis=FactScope.consolidated)


def _bound(result: BindingResult) -> dict[str, BoundInput]:
    return {item.slot: item for item in result.bound[FSS]}


def test_net_debt_is_rebound_with_the_facts_the_search_added() -> None:
    bound = _bound(complete_derived_slots(_spec(), _v8_binding(), _facts()))
    net_debt = bound["net_debt"]
    assert net_debt.value_scaled == 103584 + 1156 - 2593 - 706
    assert {"F124", "F189", "F190", "F191"} <= set(net_debt.derived_from)
    assert net_debt.missing == ["liquid investments"]
    assert "non-current lease liabilities" in net_debt.caution
    assert "lease liabilities, cash and bank balances" not in net_debt.caution


def test_debt_service_takes_cash_interest_and_principal_instead_of_the_proxy() -> None:
    bound = _bound(complete_derived_slots(_spec(), _v8_binding(), _facts()))
    debt_service = bound["debt_service"]
    assert debt_service.value_scaled == 12270 + 7403 + 1096
    assert set(debt_service.derived_from) == {"F192", "F195", "F196"}
    assert debt_service.missing == [] and "proxy" not in debt_service.caution
    assert "F031" not in debt_service.derived_from and "F007" not in debt_service.derived_from


def test_without_principal_cash_interest_replaces_the_proxy_and_the_caution_stays() -> None:
    facts = _facts(skip={"F195", "F196"})
    debt_service = _bound(complete_derived_slots(_spec(), _v8_binding(), facts))["debt_service"]
    assert debt_service.value_scaled == 12270
    assert debt_service.missing == ["scheduled principal repayments"]
    assert "missing component(s): scheduled principal repayments" in debt_service.caution


def test_the_proxy_is_kept_with_its_caution_when_nothing_is_found() -> None:
    facts = _facts(skip={"F192", "F195", "F196"})
    debt_service = _bound(complete_derived_slots(_spec(), _v8_binding(), facts))["debt_service"]
    assert debt_service.value_scaled == 8027
    assert "proxy used" in debt_service.caution


def test_a_lakh_figure_recorded_as_crore_is_flagged_not_used_silently() -> None:
    facts = _facts()
    wrong = next(f for f in facts if f.fact_id == "F189")
    statement = (
        "Consolidated current lease liabilities were 1,155.73 INR crore as at March 31, 2026."
    )
    numbers = [n.model_copy(update={"unit": "INR crore"}) for n in numeric_values_from(statement)]
    facts[facts.index(wrong)] = wrong.model_copy(
        update={"statement": statement, "numbers": numbers}
    )
    standalone = "Standalone current lease liabilities were INR 1,155.73 lakh as at March 31, 2026."
    facts.append(
        VerifiedFact(
            fact_id="F300",
            statement=standalone,
            scope=FactScope.standalone,
            numbers=numeric_values_from(standalone),
        )
    )
    net_debt = _bound(complete_derived_slots(_spec(), _v8_binding(), facts))["net_debt"]
    assert "implausible figure: F189" in net_debt.caution
    assert "standalone figure in F300" in net_debt.caution


def test_partly_bound_debt_service_searches_each_principal_row() -> None:
    facts = _facts(skip={"F192", "F195", "F196"})
    targets = [
        t for t in search_targets(_spec(), _v8_binding(), facts) if t.slot.slot == "debt_service"
    ]
    phrases = [t.phrase for t in targets]
    assert "repayment of long term borrowings" in phrases
    assert "payment of lease liabilities" in phrases
    queries = build_queries(next(t for t in targets if t.phrase.startswith("repayment")), 2026)
    joined = " | ".join(queries)
    assert "Repayment of non-current borrowings" in joined or "Repayment of term loans" in joined


def test_targets_alternate_between_slots_so_one_slot_cannot_spend_the_budget() -> None:
    facts = _facts(skip={"F189", "F190", "F191", "F192", "F195", "F196"})
    slots = [t.slot.slot for t in search_targets(_spec(), _v8_binding(), facts)]
    assert slots[:2] in (["net_debt", "debt_service"], ["debt_service", "net_debt"])
