"""Derived-slot components that are themselves bound slots take that slot's binding.

CFADS is EBITDA less cash taxes paid, and the bank's scores also bind `ebitda` as a slot of its
own (from the statement row the policy names, by code). Left to the model, the EBITDA term of
CFADS was a separate pick (a "profit before finance cost, depreciation and tax" row that holds
other income, flagged as a proxy) while the `ebitda` slot held adjusted EBITDA, so the two ratios
read different EBITDAs. `with_slot_components` runs last, after binding, the slot search and
`complete_derived_slots`: for every derived slot of a score whose component names another plain
slot of the same score (same name after normalising) that is bound, the term for that component
is that binding (same fact, same scaled value, converted only for a different slot scale), its
caution carried over with the slot name, and it never gets a proxy or outlier flag of its own.

A slot bound to one fact that states it whole (a printed CFADS) is left alone. Otherwise the
other components keep the terms the slot was summed from (`BoundInput.terms`); a component
listed as missing is filled from the facts of the run's basis when code finds it now
(`complete_derived.component_terms`). A slot that was unbound is bound this way only when every
other component is found, and a bound one is never left missing more components than before.
Everything goes through `bind_terms`, so the sum, basis and section checks are those of any
derived binding.
"""

import copy
from decimal import Decimal

from busybee.policy.bind_inputs import (
    BindingResult,
    Term,
    bind_terms,
    latest_money_year,
    term_sign,
)
from busybee.policy.complete_derived import component_terms
from busybee.policy.components import normalise_component, out_of_basis_reason, same_component
from busybee.schema.facts import FactScope, VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, ScoreSpec


def component_slot(spec: ScoreSpec, slot: InputSlot, component: str) -> InputSlot | None:
    """The plain slot of the score that a derived slot's component names, else None."""
    name = normalise_component(component)
    return next(
        (
            other
            for other in spec.inputs
            if other.slot != slot.slot
            and not other.derive_from
            and not other.mapping
            and other.judge is None
            and normalise_component(other.slot) == name
        ),
        None,
    )


def rescaled(item: BoundInput, source: InputSlot, target: InputSlot) -> int | None:
    """The bound value at the target slot's scale, or None when it is not a whole number."""
    value = Decimal(item.value_scaled) * Decimal(target.scale) / Decimal(source.scale)
    return int(value) if value == value.to_integral_value() else None


def _kept_terms(old: BoundInput | None, linked: list[str]) -> list[Term]:
    if old is None:
        return []
    return [
        Term(
            fact_id=term.fact_id,
            value=term.value,
            unit=term.unit,
            sign=term.sign,
            component=term.component,
        )
        for term in old.terms
        if not any(same_component(term.component, hint) for hint in linked)
    ]


def _rebuilt(
    slot: InputSlot,
    old: BoundInput | None,
    linked: dict[str, tuple[InputSlot, BoundInput]],
    facts: list[VerifiedFact],
    basis: FactScope,
) -> BoundInput | None:
    index = {fact.fact_id: fact for fact in facts}
    pool = [fact for fact in facts if out_of_basis_reason(fact, basis) is None]
    year = latest_money_year(facts)
    fixed: dict[str, int] = {}
    terms: list[Term] = []
    for hint, (source, item) in linked.items():
        value = rescaled(item, source, slot)
        if value is None:
            return None
        fixed[hint] = value
        sign = term_sign(slot, hint)
        terms.append(
            Term(fact_id=item.fact_id, value=item.value, unit=item.unit, sign=sign, component=hint)
        )
    kept = _kept_terms(old, list(linked))
    terms += kept
    missing: list[str] = []
    for hint in slot.derive_from:
        if hint in linked or any(same_component(term.component, hint) for term in kept):
            continue
        found, _ = component_terms(slot, hint, pool, year)
        terms += found
        missing += [] if found else [hint]
    if (old is None and missing) or (old is not None and len(missing) > len(old.missing)):
        return None
    outcome = bind_terms(slot, terms, missing, "", index, basis, fixed)
    if isinstance(outcome, str):
        return None
    carried = [
        f"{hint} as bound to the {source.slot} slot: {item.caution}"
        for hint, (source, item) in linked.items()
        if item.caution
    ]
    caution = "; ".join(part for part in (outcome.caution, *carried) if part)
    note = "; ".join(
        f"{hint} taken from the {source.slot} slot binding ({item.fact_id})"
        for hint, (source, item) in linked.items()
    )
    return outcome.model_copy(
        update={"caution": caution, "note": "; ".join(p for p in (note, caution) if p)}
    )


def with_slot_components(
    specs: list[ScoreSpec], binding: BindingResult, facts: list[VerifiedFact]
) -> BindingResult:
    """Rebind every derived slot whose component is a bound slot of its score from that binding."""
    result = copy.deepcopy(binding)
    for spec in specs:
        items = result.bound.setdefault(spec.score_id, [])
        by_slot = {item.slot: item for item in items}
        for slot in spec.inputs:
            if not slot.derive_from or slot.mapping or slot.judge is not None:
                continue
            linked = {
                hint: (other, by_slot[other.slot])
                for hint in slot.derive_from
                if (other := component_slot(spec, slot, hint)) is not None and other.slot in by_slot
            }
            old = by_slot.get(slot.slot)
            if not linked or (old is not None and not old.terms):
                continue
            better = _rebuilt(slot, old, linked, facts, result.basis)
            if better is None:
                continue
            better = better.model_copy(update={"slot": slot.slot})
            items = [*(item for item in items if item.slot != slot.slot), better]
            by_slot[slot.slot] = better
            result.unbound.pop((spec.score_id, slot.slot), None)
        result.bound[spec.score_id] = items
    return result
