"""CFADS reads the bound EBITDA slot, and cash taxes paid is searched in the cash flow (v9).

In every v9 run CFADS was cautioned, so the DSCR band was not evaluable: its EBITDA term was the
model's own pick (Indoco v9c: "profit before finance cost, depreciation ... and tax", 145.16
crore, which holds other income and was flagged a proxy) while the `ebitda` slot held adjusted
EBITDA (141.82 crore); and cash taxes paid was never found (Craftsman: the profit and loss tax
expense counted as "income tax paid", so no search target was made; Indoco: the queries named
financing activities and the cash-flow row was never among the hits). The fixtures are small
copies of those facts and passages.
"""

from decimal import Decimal

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingResult, Term, bind_terms, line_item_stated
from busybee.policy.complete_derived import complete_derived_slots
from busybee.policy.slot_components import component_slot, with_slot_components
from busybee.policy.slot_search import Target, build_queries, row_hits, search_targets
from busybee.schema.documents import Chunk
from busybee.schema.facts import FactCategory, FactScope, VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, ScoreSpec
from busybee.verify.numbers import numeric_values_from

FSS = "financial_strength_score"
CONSOLIDATED = FactScope.consolidated


def _fact(fact_id: str, statement: str, category: FactCategory) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=category,
        numbers=numeric_values_from(statement),
        scope=CONSOLIDATED,
    )


PBDIT = _fact(
    "F005",
    "Consolidated profit before finance cost, depreciation and amortisation expense and tax "
    "was INR 145.16 crore for the year ended March 31, 2026.",
    FactCategory.profitability,
)
ADJUSTED = _fact(
    "F142",
    "Consolidated adjusted EBITDA was INR 14,181.82 lakh for the year ended March 31, 2026.",
    FactCategory.profitability,
)
TAX_EXPENSE = _fact(
    "F108",
    "Consolidated income tax expense recognised in Statement of Profit & loss was INR 15,031 "
    "lakh as at Year Ended March 31, 2026 (Year Ended March 31, 2025: INR 6,878 lakh).",
    FactCategory.profitability,
)
TAX_PAID = _fact(
    "F250",
    "Consolidated income Tax Paid (Net of Refund) was an outflow of INR 616.66 lakh for the "
    "year ended March 31, 2026.",
    FactCategory.cash_flow,
)


def _spec() -> ScoreSpec:
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)
    return spec.model_copy(
        update={"inputs": [i for i in spec.inputs if i.slot in {"ebitda", "cfads"}]}
    )


def _slot(name: str) -> InputSlot:
    return next(slot for slot in _spec().inputs if slot.slot == name)


def _ebitda() -> BoundInput:
    return BoundInput(
        slot="ebitda",
        fact_id="F142",
        value=Decimal("14181.82"),
        unit="INR lakh",
        value_scaled=14182,
    )


def _model_cfads(facts: list[VerifiedFact]) -> BoundInput:
    term = Term(fact_id="F005", value=Decimal("145.16"), unit="INR crore", component="EBITDA")
    index = {fact.fact_id: fact for fact in facts}
    bound = bind_terms(_slot("cfads"), [term], ["cash taxes paid"], "", index, CONSOLIDATED)
    assert isinstance(bound, BoundInput)
    return bound


def _binding(cfads: BoundInput) -> BindingResult:
    return BindingResult(bound={FSS: [_ebitda(), cfads]}, basis=CONSOLIDATED)


def _cfads(result: BindingResult) -> BoundInput:
    return next(item for item in result.bound[FSS] if item.slot == "cfads")


def test_the_ebitda_component_names_the_ebitda_slot() -> None:
    found = component_slot(_spec(), _slot("cfads"), "ebitda")
    assert found is not None and found.slot == "ebitda"
    assert component_slot(_spec(), _slot("cfads"), "cash taxes paid") is None


def test_model_picked_ebitda_term_is_replaced_by_the_ebitda_slot_binding() -> None:
    facts = [PBDIT, ADJUSTED]
    model = _model_cfads(facts)
    assert model.value_scaled == 14516 and "proxy used" in model.caution
    cfads = _cfads(with_slot_components([_spec()], _binding(model), facts))
    assert cfads.value_scaled == 14182
    assert cfads.derived_from == ["F142"]
    assert cfads.missing == ["cash taxes paid"]
    assert "proxy" not in cfads.caution
    assert [(t.component, t.fact_id, t.value_scaled) for t in cfads.terms] == [
        ("ebitda", "F142", 14182)
    ]


def test_cash_taxes_found_in_the_cash_flow_lift_the_caution_by_absolute_value() -> None:
    facts = [PBDIT, ADJUSTED, TAX_PAID]
    cfads = _cfads(with_slot_components([_spec()], _binding(_model_cfads(facts)), facts))
    assert cfads.value_scaled == 14182 - 617
    assert cfads.missing == [] and cfads.caution == ""
    assert sorted(cfads.derived_from) == ["F142", "F250"]


def test_ebitda_slot_caution_is_carried_into_cfads() -> None:
    facts = [PBDIT, ADJUSTED]
    proxy = _ebitda().model_copy(update={"caution": "proxy used: stand-in row"})
    binding = BindingResult(bound={FSS: [proxy, _model_cfads(facts)]}, basis=CONSOLIDATED)
    cfads = _cfads(with_slot_components([_spec()], binding, facts))
    assert "ebitda as bound to the ebitda slot: proxy used: stand-in row" in cfads.caution


def test_a_cfads_stated_whole_by_one_fact_is_left_alone() -> None:
    whole = BoundInput(slot="cfads", fact_id="F077", value=Decimal("120.5"), value_scaled=12050)
    result = with_slot_components([_spec()], _binding(whole), [ADJUSTED])
    assert _cfads(result) == whole


def test_completion_keeps_the_terms_it_merges() -> None:
    facts = [PBDIT, ADJUSTED, TAX_PAID]
    done = _cfads(complete_derived_slots([_spec()], _binding(_model_cfads(facts)), facts))
    assert {t.fact_id for t in done.terms} == {"F005", "F250"}


def test_tax_expense_is_not_income_tax_paid_so_the_search_targets_it() -> None:
    assert not line_item_stated("income tax paid", "cash taxes paid", [TAX_EXPENSE], CONSOLIDATED)
    assert line_item_stated("income tax paid", "cash taxes paid", [TAX_PAID], CONSOLIDATED)
    binding = BindingResult(bound={FSS: []}, basis=CONSOLIDATED)
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)
    targets = search_targets([spec], binding, [TAX_EXPENSE], CONSOLIDATED)
    phrases = [(t.slot.slot, t.phrase) for t in targets]
    assert ("cfads", "income tax paid") in phrases
    cautions = [p for p in phrases if p[0] in {"cfads", "net_debt", "tangible_net_worth"}]
    assert cautions[0] == ("cfads", "income tax paid")


def test_tax_queries_name_operating_activities_and_the_usual_wordings() -> None:
    target = Target(_slot("cfads"), (FSS,), "income tax paid", True, "consolidated")
    queries = build_queries(target, 2026)
    assert queries[0].startswith("consolidated Income taxes paid (net of refunds) cash flow from")
    assert "operating activities" in queries[0] and "financing" not in queries[0]
    assert queries[1].startswith("consolidated Direct taxes paid (net)")


def _chunk(chunk_id: str, page: int, text: str) -> Chunk:
    index = int(chunk_id.rsplit("c", 1)[1])
    return Chunk(chunk_id=chunk_id, doc_id="D1", page_no=page, index_in_page=index, text=text)


def test_row_hits_are_cash_flow_statement_rows_only() -> None:
    chunks = [
        _chunk("D1:p273:c0", 273, "Consolidated Cash Flow Statement\n(A) Cash Flow from Operating"),
        _chunk(
            "D1:p273:c1",
            273,
            "Cash generated from Operations | 20,133.97 | 11,106.54\n"
            "Income Tax Paid (Net of Refund) | (616.66) | (1,712.20)",
        ),
        _chunk("D1:p296:c0", 296, "Add: Taxes paid (net) | March 31, 2026: 1,246.96"),
        _chunk("D1:p150:c0", 150, "Income tax paid | 616.66"),
    ]
    target = Target(_slot("cfads"), (FSS,), "income tax paid", True, "consolidated")
    assert [chunk.chunk_id for chunk, _ in row_hits(target, chunks)] == ["D1:p273:c1"]
    other = Target(_slot("cfads"), (FSS,), "ebitda", True, "consolidated")
    assert row_hits(other, chunks) == []
