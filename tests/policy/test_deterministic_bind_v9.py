"""Indoco v9a/v9b regression: two identical runs gave Financial Strength Score 28 and 16.

The fixture holds the score-input facts of both runs as saved. v9b bound EBITDA to profit before
finance cost and depreciation (145.16 crore, which includes other income) and v9a to adjusted
EBITDA (141.82 crore); interest expense was the profit and loss finance cost (122.25 crore) in
v9b but the narrower interest-expense row (80.27 crore) in v9a, because v9a's relevance filter
had dropped every copy of the finance-cost row as a "duplicate". Code now picks these rows the
same way every run, a model note no longer makes a full total-debt definition a proxy, the
consolidated cash row is searched for and read, and a lone duplicate survives the relevance
filter.
"""

import json
import random
from decimal import Decimal
from pathlib import Path

from policy_helpers import BANKS_DIR

from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import (
    BindingOutput,
    BindingResult,
    bind_inputs,
    item_figure,
    line_item_stated,
    statement_row_binding,
    validate_bindings,
)
from busybee.policy.complete_derived import complete_derived_slots
from busybee.policy.slot_search import build_queries, search_targets
from busybee.schema.facts import FactCategory, FactScope, NotebookEntry, VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, ScoreSpec
from busybee.verify.relevance import DROP_REASONS, RelevanceDecision, keep_lone_duplicates

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_v9_bind_facts.json"
FSS = "financial_strength_score"
CONSOLIDATED = FactScope.consolidated


def _facts(run: str) -> list[VerifiedFact]:
    return [VerifiedFact.model_validate(item) for item in json.loads(FIXTURE.read_text())[run]]


def _fss() -> ScoreSpec:
    return next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)


def _slot(name: str) -> InputSlot:
    return next(slot for slot in _fss().inputs if slot.slot == name)


def _only(*names: str) -> list[ScoreSpec]:
    spec = _fss()
    return [spec.model_copy(update={"inputs": [i for i in spec.inputs if i.slot in names]})]


def test_interest_expense_is_the_profit_and_loss_finance_cost_in_any_fact_order() -> None:
    facts = _facts("v9b")
    for seed in range(5):
        random.Random(seed).shuffle(facts)
        bound = statement_row_binding(_slot("interest_expense"), facts, CONSOLIDATED)
        assert bound is not None
        assert (bound.fact_id, bound.value_scaled, bound.caution) == ("F008", 12225, "")


def test_without_a_finance_cost_row_interest_expense_is_a_proxy_never_the_cash_outflow() -> None:
    bound = statement_row_binding(_slot("interest_expense"), _facts("v9a"), CONSOLIDATED)
    assert bound is not None and bound.fact_id == "F268"
    assert bound.caution.startswith("proxy used: F268 is the interest expense row")


def test_ebitda_is_the_ebitda_row_not_profit_before_finance_cost_with_other_income() -> None:
    for run, fact_id in (("v9a", "F139"), ("v9b", "F137")):
        bound = statement_row_binding(_slot("ebitda"), _facts(run), CONSOLIDATED)
        assert bound is not None
        assert (bound.fact_id, bound.value_scaled, bound.caution) == (fact_id, 14182, "")


async def test_the_code_choice_replaces_the_models_pick() -> None:
    facts = _facts("v9b")
    reply = {
        "bindings": [
            {"score_id": FSS, "slot": "ebitda", "fact_id": "F006", "value": "145.16"},
            {"score_id": FSS, "slot": "interest_expense", "fact_id": "F266", "value": "12270.29"},
        ]
    }
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)] * 2})
    result = await bind_inputs(provider, _only("ebitda", "interest_expense"), facts)
    bound = {item.slot: item for item in result.bound[FSS]}
    assert bound["ebitda"].fact_id == "F137"
    assert bound["interest_expense"].fact_id == "F008"


def test_a_model_proxy_note_on_the_full_total_debt_definition_sets_no_caution() -> None:
    terms = [
        {
            "fact_id": "F178",
            "value": "103584.47",
            "unit": "INR lakh",
            "component": "total borrowings",
        },
        {
            "fact_id": "F265",
            "value": "4233.88",
            "unit": "INR lakh",
            "component": "lease liabilities",
        },
        {
            "fact_id": "F268",
            "value": "1155.73",
            "unit": "INR lakh",
            "component": "lease liabilities",
        },
    ]
    output = BindingOutput.model_validate(
        {
            "bindings": [
                {
                    "score_id": FSS,
                    "slot": "total_debt",
                    "terms": terms,
                    "note": "Sum of consolidated total borrowings and lease liabilities.",
                }
            ]
        }
    )
    facts = {fact.fact_id: fact for fact in _facts("v9b")}
    result = validate_bindings(output, _only("total_debt"), facts, CONSOLIDATED)
    total_debt = result.bound[FSS][0]
    assert total_debt.value_scaled == 108974
    assert total_debt.caution == ""


def test_a_lease_payment_for_lease_liabilities_is_flagged_by_code() -> None:
    terms = [
        {
            "fact_id": "F178",
            "value": "103584.47",
            "unit": "INR lakh",
            "component": "total borrowings",
        },
        {
            "fact_id": "F110",
            "value": "-1095.62",
            "unit": "INR lakh",
            "component": "lease liabilities",
        },
    ]
    output = BindingOutput.model_validate(
        {"bindings": [{"score_id": FSS, "slot": "total_debt", "terms": terms}]}
    )
    facts = {fact.fact_id: fact for fact in _facts("v9b")}
    item = validate_bindings(output, _only("total_debt"), facts, CONSOLIDATED).bound[FSS][0]
    assert "proxy used: F110 is a cash flow, not the lease liabilities balance" in item.caution


def test_bank_balances_other_than_cash_do_not_state_cash_and_cash_equivalents() -> None:
    facts = _facts("v9b")
    assert not line_item_stated(
        "cash and cash equivalents", "cash and bank balances", facts, CONSOLIDATED
    )
    assert line_item_stated(
        "bank balances other than cash and cash equivalents",
        "cash and bank balances",
        facts,
        CONSOLIDATED,
    )
    binding = BindingResult(bound={FSS: []}, basis=CONSOLIDATED)
    phrases = {t.phrase for t in search_targets(_only("net_debt"), binding, facts, CONSOLIDATED)}
    assert "cash and cash equivalents" in phrases


def test_a_cash_row_naming_the_company_before_its_figure_is_read() -> None:
    fact = next(f for f in _facts("v9a") if f.fact_id == "F274")
    number = item_figure(fact, "cash and cash equivalents", 2026)
    assert number is not None and number.value == Decimal("2592.78")


def test_v9a_net_debt_is_completed_with_the_cash_the_search_found() -> None:
    old = BoundInput(
        slot="net_debt",
        fact_id="F156",
        value=Decimal("1082.68"),
        unit="INR crore x 100",
        value_scaled=108268,
        derived_from=["F156", "F267", "F271", "F276"],
        caution="missing component(s): cash and bank balances, liquid investments",
        missing=["cash and bank balances", "liquid investments"],
    )
    binding = BindingResult(bound={FSS: [old]}, basis=CONSOLIDATED)
    done = complete_derived_slots(_only("net_debt"), binding, _facts("v9a"))
    net_debt = done.bound[FSS][0]
    assert "F274" in net_debt.derived_from and "F276" in net_debt.derived_from
    assert net_debt.missing == ["liquid investments"]
    assert net_debt.value_scaled == 108268 - 2593


def test_interest_expense_is_searched_as_finance_cost_in_the_profit_and_loss() -> None:
    binding = BindingResult(
        bound={FSS: []}, unbound={(FSS, "interest_expense"): "not bound"}, basis=CONSOLIDATED
    )
    targets = search_targets(_only("interest_expense"), binding, _facts("v9a"), CONSOLIDATED)
    assert [t.phrase for t in targets] == ["finance cost"]
    queries = build_queries(targets[0], 2026)
    assert "consolidated finance cost statement of profit and loss FY2026" in queries


def _entry(entry_id: str, statement: str) -> NotebookEntry:
    return NotebookEntry(
        entry_id=entry_id, statement=statement, category=FactCategory.liquidity, doc_id="D1"
    )


def test_when_every_copy_is_called_a_duplicate_the_first_survives() -> None:
    entries = [
        _entry("E1", "Consolidated cash and cash equivalents was INR 2,592.78 lakh as at 2026."),
        _entry("E2", "Consolidated total, Cash and Cash Equivalents was INR 2,592.78 lakh."),
        _entry("E3", "Standalone cash and cash equivalents was INR 1,111.11 lakh."),
        _entry("E4", "Standalone cash and cash equivalents were INR 1,111.11 lakh in 2026."),
    ]
    dup = DROP_REASONS["dup"]
    decisions = {
        "E1": RelevanceDecision(entry_id="E1", keep=False, reason=dup),
        "E2": RelevanceDecision(entry_id="E2", keep=False, reason=dup),
        "E3": RelevanceDecision(entry_id="E3", keep=True, reason="kept"),
        "E4": RelevanceDecision(entry_id="E4", keep=False, reason=dup),
    }
    kept = {key for key, value in keep_lone_duplicates(entries, decisions).items() if value.keep}
    assert kept == {"E1", "E3"}
