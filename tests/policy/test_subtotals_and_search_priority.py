"""Unlabelled balance-sheet subtotals and slot-search priority (Craftsman v9).

Craftsman's consolidated balance sheet prints total current assets as a row of figures without
a label, so current assets stayed unbound and no score was computable. The subtotal is now
computed from the printed totals it equals, and the slot search looks for those totals. The
search also spent its 40 calls on components that only add a caution (intangibles, cash taxes)
interleaved with slots that block a score; blocking targets now go first and the budget is 60.
"""

from decimal import Decimal

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingResult
from busybee.policy.slot_search import DEFAULT_BUDGET, search_targets
from busybee.policy.subtotals import subtotal_binding, subtotal_search_rows, with_subtotals
from busybee.schema.facts import FactCategory, FactScope, VerifiedFact
from busybee.schema.policy import ScoreSpec

FSS = "financial_strength_score"
CONSOLIDATED = FactScope.consolidated


def _fss() -> ScoreSpec:
    return next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)


def _slot(name: str):
    return next(slot for slot in _fss().inputs if slot.slot == name)


def _fact(
    fact_id: str, label: str, value: str, unit: str, category=FactCategory.liquidity
) -> VerifiedFact:
    printed = f"{Decimal(value):,}"
    return VerifiedFact(
        fact_id=fact_id,
        statement=f"Consolidated {label} was INR {printed} {unit} as at March 31, 2026.",
        category=category,
        numbers=[{"label": label, "value": value, "unit": f"INR {unit}", "period": "2026"}],
    )


def _balance_sheet() -> list[VerifiedFact]:
    return [
        _fact("F1", "total assets", "897830", "lakh"),
        _fact("F2", "total non-current assets", "5356.55", "crore"),
        _fact("F3", "other non-current assets", "20380", "lakh"),
        _fact("F4", "total equity and liabilities", "897830", "lakh"),
        _fact("F5", "total equity", "326406", "lakh"),
        _fact("F6", "total non-current liabilities", "264935", "lakh"),
        *(_fact(f"F{n}", f"item {n}", str(n), "lakh") for n in range(10, 16)),
    ]


def test_current_assets_are_total_assets_less_non_current_assets_converted_first() -> None:
    bound = subtotal_binding(_slot("current_assets"), _balance_sheet(), CONSOLIDATED)
    assert bound is not None
    assert bound.value_scaled == 897830 - 535655
    assert bound.derived_from == ["F1", "F2"]
    assert bound.caution == ""
    assert bound.note.startswith("derived from printed totals: total assets (F1)")


def test_current_liabilities_use_equity_and_liabilities_when_no_total_liabilities() -> None:
    bound = subtotal_binding(_slot("current_liabilities"), _balance_sheet(), CONSOLIDATED)
    assert bound is not None
    assert bound.value_scaled == 897830 - 326406 - 264935
    assert bound.derived_from == ["F4", "F5", "F6"]


def test_no_subtotal_without_every_total_or_from_another_basis_or_a_cash_flow() -> None:
    facts = [f for f in _balance_sheet() if f.fact_id != "F2"]
    assert subtotal_binding(_slot("current_assets"), facts, CONSOLIDATED) is None
    standalone = [f.model_copy(update={"scope": FactScope.standalone}) for f in _balance_sheet()]
    assert subtotal_binding(_slot("current_assets"), standalone, CONSOLIDATED) is None
    flow = _fact("F2", "total non-current assets", "5356.55", "crore", FactCategory.cash_flow)
    flow = flow.model_copy(update={"statement": flow.statement.replace("was", "paid was")})
    facts = [flow if f.fact_id == "F2" else f for f in _balance_sheet()]
    assert subtotal_binding(_slot("current_assets"), facts, CONSOLIDATED) is None


def test_with_subtotals_binds_only_unbound_subtotal_slots() -> None:
    binding = BindingResult(
        bound={FSS: []},
        unbound={(FSS, "current_assets"): "no fact", (FSS, "interest_expense"): "no fact"},
        basis=CONSOLIDATED,
    )
    result = with_subtotals([_fss()], binding, _balance_sheet())
    assert [item.slot for item in result.bound[FSS]] == ["current_assets"]
    assert list(result.unbound) == [(FSS, "interest_expense")]
    assert (FSS, "current_assets") in binding.unbound


def test_search_looks_for_blocking_slots_and_their_totals_before_caution_components() -> None:
    assert DEFAULT_BUDGET == 60
    assert subtotal_search_rows(_slot("current_assets")) == [
        "total assets",
        "total non-current assets",
    ]
    binding = BindingResult(
        bound={FSS: []},
        unbound={(FSS, "current_assets"): "x", (FSS, "interest_expense"): "x"},
        basis=CONSOLIDATED,
    )
    targets = search_targets([_fss()], binding, [], CONSOLIDATED)
    blocking = {"current_assets", "interest_expense"}
    first = [t.slot.slot in blocking for t in targets]
    assert first == sorted(first, reverse=True)
    phrases = [t.phrase for t in targets if t.slot.slot == "current_assets"]
    assert phrases == ["current assets", "total assets", "total non-current assets"]
    assert any(t.slot.slot not in blocking for t in targets)
