"""Craftsman v9 regression: no score was computable because table units came from the model.

The consolidated balance sheet is headed "(H in lakhs)" (a rupee sign extracted as a letter),
which the header reader missed, so slot search recorded total equity 3,26,406 and the lease
liabilities 20,778 / 7,507 as crore. Total debt then summed lakh and crore figures, the model
noted a "unit mismatch", and tangible net worth came out 100x too large. The implausible-figure
guard also fired on correct figures: EBITDA 1,300.07 crore against a 2019 EBITDA *decrease* in
an offer document, borrowings against net proceeds from short-term borrowings (a cash flow).
The pack's latest year was read as 2020 (that offer document states more consolidated figures
than the annual report), and FY2025-26 was read as 2025, so the EBITDA row was never bound by
code. Debt service summed outflows printed in brackets as negative numbers.
"""

import json
from decimal import Decimal
from pathlib import Path

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import (
    Term,
    _period_year,
    _reference_year,
    bind_terms,
    statement_row_binding,
)
from busybee.policy.components import out_of_basis_reason, outlier_reason
from busybee.schema.documents import Chunk
from busybee.schema.facts import FactScope, VerifiedFact
from busybee.schema.policy import InputSlot
from busybee.verify.table_units import (
    chunk_unit,
    facts_with_header_units,
    last_unit,
    page_index,
    with_header_units,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "craftsman_v9_units.json").read_text(encoding="utf-8")
)
CONSOLIDATED = FactScope.consolidated


def _chunks() -> dict[str, Chunk]:
    return {item["chunk_id"]: Chunk.model_validate(item) for item in FIXTURE["chunks"]}


def _facts() -> dict[str, VerifiedFact]:
    return {item["fact_id"]: VerifiedFact.model_validate(item) for item in FIXTURE["facts"]}


def _fixed() -> dict[str, VerifiedFact]:
    return {f.fact_id: f for f in facts_with_header_units(_facts().values(), _chunks())}


def _slot(score: str, name: str) -> InputSlot:
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == score)
    return next(slot for slot in spec.inputs if slot.slot == name)


def test_a_rupee_sign_extracted_as_a_letter_still_names_the_unit() -> None:
    assert last_unit("(H in lakhs)\nConsolidated Balance Sheet") == "lakh"
    assert last_unit("(D in Crores)\nParticulars") == "crore"
    assert last_unit("(as in the previous year)") == ""
    chunks = _chunks()
    page = [c for c in chunks.values() if c.page_no == 176]
    assert chunk_unit(chunks["D1:p176:c1"], page, "3,26,406") == "lakh"


def test_slot_search_figures_take_the_balance_sheet_header_unit() -> None:
    fixed = _fixed()
    equity = fixed["F291"]
    assert (
        equity.statement == "Consolidated total equity was INR 3,26,406 lakh as at March 31, 2026."
    )
    assert equity.numbers[0].unit == "INR lakh"
    assert "unit from table header" in equity.verification.notes
    assert "326406 crore -> lakh" in equity.verification.notes
    assert fixed["F292"].numbers[0].unit == "INR lakh"
    assert fixed["F293"].numbers[0].unit == "INR lakh"


def test_header_agreeing_rows_prose_and_rows_naming_their_unit_are_left_alone() -> None:
    facts, fixed = _facts(), _fixed()
    for fact_id in ("F004", "F109", "F094", "F191", "F145"):
        assert fixed[fact_id] == facts[fact_id]


def test_a_unit_the_statement_prints_after_an_unscaled_number_is_overridden_too() -> None:
    chunks = _chunks()
    fact = _facts()["F293"].model_copy(
        update={
            "statement": "Consolidated current lease liabilities were 7,507 INR crore in 2026.",
            "numbers": [_facts()["F293"].numbers[0].model_copy(update={"unit": ""})],
        }
    )
    fixed = with_header_units(fact, chunks, page_index(chunks.values()))
    assert fixed.statement == "Consolidated current lease liabilities were 7,507 INR lakh in 2026."
    assert fixed.numbers[0].unit == "INR lakh"


def test_total_debt_sums_lakh_and_crore_terms_after_converting_each() -> None:
    slot = _slot("financial_strength_score", "total_debt")
    facts = _fixed()
    terms = [
        Term(fact_id="F109", value=Decimal(334063), unit="INR lakh", component=c, sign=1)
        for c in ("total borrowings",)
    ] + [
        Term(fact_id=fid, value=Decimal(v), unit="INR lakh", component="lease liabilities", sign=1)
        for fid, v in (("F292", 20778), ("F293", 7507))
    ]
    missing = [h for h in slot.derive_from if h not in ("total borrowings", "lease liabilities")]
    bound = bind_terms(slot, terms, missing, "", facts, CONSOLIDATED)
    assert not isinstance(bound, str)
    assert bound.value_scaled == 362348
    assert "implausible" not in bound.caution
    crore = facts["F004"].model_copy(update={"fact_id": "FX", "scope": CONSOLIDATED})
    mixed = [
        terms[0],
        Term(fact_id="FX", value=Decimal("1300.07"), unit="INR crore", component="lease", sign=1),
    ]
    summed = bind_terms(slot, mixed, missing, "", {**facts, "FX": crore}, CONSOLIDATED)
    assert not isinstance(summed, str)
    assert summed.value_scaled == 334063 + 130007


def test_outflows_in_brackets_enter_debt_service_with_their_absolute_figure() -> None:
    slot = _slot("financial_strength_score", "debt_service")
    terms = [
        Term(fact_id=fid, value=Decimal(v), unit="INR lakh", component=component, sign=1)
        for fid, v, component in (
            ("F102", -31167, slot.derive_from[0]),
            ("F103", -42396, slot.derive_from[1]),
            ("F104", -13537, slot.derive_from[1]),
        )
    ]
    bound = bind_terms(slot, terms, [], "", _fixed(), CONSOLIDATED)
    assert not isinstance(bound, str)
    assert bound.value_scaled == 31167 + 42396 + 13537


def test_the_guard_compares_like_for_like_only() -> None:
    facts = _fixed()
    ebitda = facts["F004"]
    assert outlier_reason("ebitda", ebitda, ebitda.numbers[0], facts.values()) is None
    debt = facts["F109"]
    assert outlier_reason("total borrowings", debt, debt.numbers[0], facts.values()) is None
    lease = facts["F292"]
    assert outlier_reason("lease liabilities", lease, lease.numbers[0], facts.values()) is None
    wrong = _facts()["F292"]
    others = [*(f for f in facts.values() if f.fact_id != "F292"), wrong]
    previous = facts["F098"].model_copy(
        update={
            "fact_id": "FL",
            "statement": "Consolidated lease liabilities were INR 30,392 lakh at March 31, 2025.",
            "numbers": [
                facts["F098"]
                .numbers[1]
                .model_copy(update={"label": "lease liabilities", "value": Decimal(30392)})
            ],
            "record": None,
        }
    )
    assert outlier_reason("lease liabilities", wrong, wrong.numbers[0], [*others, previous])


def test_fy2025_26_closes_in_2026_and_an_old_offer_document_does_not_set_the_year() -> None:
    assert _period_year("FY2025-26") == 2026
    assert _period_year("FY24-25") == 2025
    facts = [f for f in _fixed().values() if out_of_basis_reason(f, CONSOLIDATED) is None]
    old = [
        VerifiedFact(
            fact_id=f"O{n}",
            statement=f"Consolidated item {n} was INR {n}.5 million in Fiscal 2020.",
            numbers=[{"label": "item", "value": f"{n}.5", "unit": "INR million", "period": "2020"}],
        )
        for n in range(40)
    ]
    assert _reference_year([*facts, *old]) == 2026
    bound = statement_row_binding(
        _slot("financial_strength_score", "ebitda"), [*facts, *old], CONSOLIDATED
    )
    assert bound is not None and (bound.fact_id, bound.value_scaled) == ("F004", 130007)
