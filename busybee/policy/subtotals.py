"""Compute a balance-sheet subtotal slot from printed totals when no fact states it.

Schedule III balance sheets often print the current-assets or current-liabilities subtotal as
a row of figures without a label, so neither the extractor nor the slot search can name it,
while the labelled totals around it are read fine. For a plain slot listed in
`components.SUBTOTAL_FORMULAS` that is still unbound, `subtotal_binding` tries each formula
(current assets = total assets - total non-current assets; current liabilities = total
liabilities - non-current liabilities, or total equity and liabilities - total equity -
non-current liabilities): every row must be stated by a fact of the run's basis whose label is
exactly that row (`bind_inputs.label_is`), not a cash flow, with one consistent figure for the
latest audited year. Each figure is scaled to the slot's unit first, then summed with its sign,
in code. The result must be positive; it is cited to every input fact (`derived_from`), noted
as derived with the formula, and carries no proxy caution: it is the same quantity, computed.
Before any formula, a fact of the basis whose label is exactly the subtotal itself ("total
current assets") binds it as stated: such a fact is the printed section total read from the
balance sheet in code (`section_totals`), which also catches a total that the formulas would
miss, such as current assets printed without the assets held for sale that total assets
include. When that fact was computed as the sum of the section's rows (`section_row_sum`) the
binding is cited to it as derived and says so.
`with_subtotals` applies this to every unbound subtotal slot of a `BindingResult` and is run
after each bind (`run_scores`, `tools/replay_scores.py`). `subtotal_search_rows` names the
totals the slot search looks for while such a slot is unbound.
"""

import copy
from decimal import Decimal

from busybee.policy.bind_inputs import (
    BindingResult,
    item_figure,
    label_is,
    latest_money_year,
    score_input_slots,
)
from busybee.policy.components import (
    normalise_component,
    out_of_basis_reason,
    states_flow,
    subtotal_formulas,
)
from busybee.policy.scaling import ScalingError, to_scaled_int
from busybee.policy.section_totals import SUM_METHOD
from busybee.schema.facts import FactScope, VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, ScoreSpec


def _row_figure(
    slot: InputSlot, wordings: tuple[str, ...], facts: list[VerifiedFact], year: int
) -> tuple[VerifiedFact, int] | None:
    """The one scaled figure the facts state for the row in the year, with its first fact."""
    found: list[tuple[VerifiedFact, int]] = []
    for wording in wordings:
        for fact in facts:
            if states_flow(fact) or not label_is(fact, wording):
                continue
            number = item_figure(fact, wording, year)
            if number is None:
                continue
            try:
                found.append((fact, to_scaled_int(number.value, number.unit, slot)))
            except ScalingError:
                continue
        if found:
            break
    return found[0] if found and len({value for _, value in found}) == 1 else None


def _own_row_binding(slot: InputSlot, pool: list[VerifiedFact], year: int) -> BoundInput | None:
    """Bind the slot from a fact that states the subtotal itself, else None."""
    row = normalise_component(slot.slot)
    found = _row_figure(slot, (f"total {row}", row), pool, year)
    if found is None:
        return None
    fact, value = found
    if value <= 0:
        return None
    summed = fact.verification is not None and fact.verification.method == SUM_METHOD
    note = (
        f"derived: sum of the printed rows of the {row} section ({fact.fact_id})"
        if summed
        else f"printed {row} total ({fact.fact_id})"
    )
    return BoundInput(
        slot=slot.slot,
        fact_id=fact.fact_id,
        value=Decimal(value) / Decimal(slot.scale),
        unit=slot.unit,
        value_scaled=value,
        derived_from=[fact.fact_id] if summed else [],
        note=note,
    )


def subtotal_binding(
    slot: InputSlot, facts: list[VerifiedFact], basis: FactScope
) -> BoundInput | None:
    """Bind a subtotal slot from its own printed total or the printed totals it equals, or None."""
    pool = [fact for fact in facts if out_of_basis_reason(fact, basis) is None]
    year = latest_money_year(facts)
    own = _own_row_binding(slot, pool, year) if subtotal_formulas(slot) else None
    if own is not None:
        return own
    for formula in subtotal_formulas(slot):
        rows = [
            (sign, wordings, _row_figure(slot, wordings, pool, year)) for sign, wordings in formula
        ]
        if any(found is None for _, _, found in rows):
            continue
        total = sum(sign * found[1] for sign, _, found in rows if found is not None)
        if total <= 0:
            continue
        used = [found[0].fact_id for _, _, found in rows if found is not None]
        formula_text = " ".join(
            f"{'+' if sign > 0 else '-'} {wordings[0]} ({fact_id})"
            for (sign, wordings, _), fact_id in zip(rows, used, strict=True)
        ).lstrip("+ ")
        return BoundInput(
            slot=slot.slot,
            fact_id=used[0],
            value=Decimal(total) / Decimal(slot.scale),
            unit=slot.unit,
            value_scaled=total,
            derived_from=list(dict.fromkeys(used)),
            note=f"derived from printed totals: {formula_text}",
        )
    return None


def with_subtotals(
    specs: list[ScoreSpec], binding: BindingResult, facts: list[VerifiedFact]
) -> BindingResult:
    """The binding with every unbound subtotal slot computed from printed totals where possible."""
    result = copy.deepcopy(binding)
    for spec, slot in score_input_slots(specs):
        key = (spec.score_id, slot.slot)
        if key not in result.unbound or not subtotal_formulas(slot):
            continue
        if any(item.slot == slot.slot for item in result.bound.get(spec.score_id, [])):
            result.unbound.pop(key)
            continue
        bound = subtotal_binding(slot, facts, result.basis)
        if bound is not None:
            result.bound.setdefault(spec.score_id, []).append(bound)
            result.unbound.pop(key)
    return result


def subtotal_search_rows(slot: InputSlot) -> list[str]:
    """The printed totals the slot search looks for to compute the subtotal slot."""
    rows = [wordings[0] for formula in subtotal_formulas(slot) for _, wordings in formula]
    return list(dict.fromkeys(rows))
