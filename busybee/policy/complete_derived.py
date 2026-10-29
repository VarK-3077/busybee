"""Rebind derived slots deterministically once the slot search has added facts.

The binder may have bound a derived slot (net debt, debt service, CFADS) before the slot search
recovered the facts it lacked: net debt computed without lease liabilities and cash, debt service
from an interest-expense proxy without principal repayments. `complete_derived_slots` revisits
every derived slot that is unbound, has missing components or carries a proxy caution, and builds
two candidates from the facts of the run's basis only (never mixing consolidated and standalone):

* merged: the earlier value plus signed terms for the components it listed as missing and that
  a fact now supplies (the earlier terms are kept, so a total the patterns cannot read is not lost,
  and a fact already among them, such as a partial cash row, is never added a second time);
* from scratch: one term set per component, each component either a single fact stating the
  component total or the sum of its statement rows (`LINE_ITEMS`, matched with every wording in
  `ITEM_WORDINGS`), every row taken only when one figure for the latest year is stated.

Components read from the cash-flow statement (interest paid, principal repayments, taxes paid)
take only cash-flow facts (category cash_flow, or a statement that says paid or repayment), so a
profit and loss finance cost never re-enters as interest paid, and their figures are taken as
magnitudes (outflows are printed in brackets). A component whose rows are only partly found (current
lease liabilities without the non-current part) is used with a caution naming the missing row.
The candidate with the fewest missing components wins, then the one without a proxy, then the one
with fewer partial components; on a tie the earlier binding stays. A slot that was unbound is
only bound from scratch when every component is found. Every term goes through `bind_terms`, so
basis, section, scaling and the implausible-figure guard apply exactly as for a model answer.
"""

import copy
from decimal import Decimal

from busybee.policy.bind_inputs import (
    BindingResult,
    Term,
    bind_terms,
    derived_caution,
    item_figure,
    latest_money_year,
    score_input_slots,
    term_sign,
)
from busybee.policy.components import (
    is_cash_flow_component,
    item_wordings,
    line_items,
    out_of_basis_reason,
    wrong_section_reason,
)
from busybee.schema.facts import FactCategory, FactScope, VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, ScoreSpec

_PROXY = "proxy used:"
_FLOW_WORDS = ("paid", "repayment", "payment", "cash flow", "outflow")
_IMPLAUSIBLE = "implausible figure:"


def _flow_fact(fact: VerifiedFact) -> bool:
    text = fact.statement.lower()
    return fact.category is FactCategory.cash_flow or any(word in text for word in _FLOW_WORDS)


def _row_terms(
    slot: InputSlot, component: str, row: str, pool: list[VerifiedFact], year: int
) -> list[Term]:
    """One term for the row when every fact stating it for the year gives the same figure."""
    flow = is_cash_flow_component(component)
    found: dict[str, Term] = {}
    for fact in pool:
        if flow and not _flow_fact(fact):
            continue
        if wrong_section_reason(component, fact):
            continue
        for wording in item_wordings(row):
            number = item_figure(fact, wording, year)
            if number is None:
                continue
            value = abs(number.value) if flow else number.value
            found.setdefault(
                fact.fact_id,
                Term(
                    fact_id=fact.fact_id,
                    value=value,
                    unit=number.unit,
                    sign=term_sign(slot, component),
                    component=component,
                ),
            )
            break
    values = {term.value.normalize() for term in found.values()}
    return list(found.values())[:1] if len(values) == 1 else []


def _states_a_row(fact: VerifiedFact, rows: tuple[str, ...], year: int) -> bool:
    return any(
        item_figure(fact, wording, year) is not None
        for row in rows
        for wording in item_wordings(row)
    )


def component_terms(
    slot: InputSlot, component: str, pool: list[VerifiedFact], year: int
) -> tuple[list[Term], list[str]]:
    """The terms for a component and the rows of it that no fact states (empty when none found)."""
    rows = line_items(component)
    if len(rows) > 1:
        totals = [fact for fact in pool if not _states_a_row(fact, rows, year)]
        total = _row_terms(slot, component, component, totals, year)
        if total:
            return total, []
    terms: list[Term] = []
    absent: list[str] = []
    for row in rows:
        found = _row_terms(slot, component, row, pool, year)
        terms += found
        if not found:
            absent.append(row)
    return (terms, absent) if terms else ([], list(rows))


def _rank(item: BoundInput, partial: int) -> tuple[int, bool, int]:
    return len(item.missing), _PROXY in item.caution, partial


def _proxy_note(caution: str) -> str:
    at = caution.find(_PROXY)
    if at < 0:
        return ""
    return caution[at + len(_PROXY) :].split(f"; {_IMPLAUSIBLE}")[0].strip()


def _partial_lines(partial: dict[str, list[str]]) -> list[str]:
    return [
        f"{component} taken without {', '.join(rows)} (not found)"
        for component, rows in partial.items()
    ]


def _implausible(caution: str) -> list[str]:
    return [part for part in caution.split("; ") if part.startswith(_IMPLAUSIBLE)]


def _finish(
    item: BoundInput, missing: list[str], proxy: str, partial: dict[str, list[str]], note: str
) -> BoundInput:
    proxies = "; ".join(dict.fromkeys(p for p in (proxy, _proxy_note(item.caution)) if p))
    caution = derived_caution(
        missing, proxies, [*_implausible(item.caution), *_partial_lines(partial)]
    )
    return item.model_copy(
        update={
            "missing": missing,
            "caution": caution,
            "note": "; ".join(p for p in (note, caution) if p),
        }
    )


def _from_scratch(
    slot: InputSlot,
    found: dict[str, tuple[list[Term], list[str]]],
    index: dict[str, VerifiedFact],
    basis: FactScope,
) -> tuple[BoundInput, int] | None:
    terms = [term for hint in slot.derive_from for term in found[hint][0]]
    if not terms:
        return None
    missing = [hint for hint in slot.derive_from if not found[hint][0]]
    partial = {h: found[h][1] for h in slot.derive_from if found[h][0] and found[h][1]}
    outcome = bind_terms(slot, terms, missing, "", index, basis)
    if isinstance(outcome, str):
        return None
    note = "rebound after slot search from " + ", ".join(
        f"{term.component} ({term.fact_id})" for term in terms
    )
    return _finish(outcome, missing, "", partial, note), len(partial)


def _merged(
    slot: InputSlot,
    old: BoundInput,
    found: dict[str, tuple[list[Term], list[str]]],
    index: dict[str, VerifiedFact],
    basis: FactScope,
) -> tuple[BoundInput, int] | None:
    filled = [hint for hint in slot.derive_from if hint in old.missing and found[hint][0]]
    if not filled:
        return None
    terms = [
        term for hint in filled for term in found[hint][0] if term.fact_id not in old.derived_from
    ]
    if not terms:
        return None
    others = [hint for hint in slot.derive_from if hint not in filled]
    part = bind_terms(slot, terms, others, "", index, basis)
    if isinstance(part, str):
        return None
    total = old.value_scaled + part.value_scaled
    missing = [hint for hint in old.missing if hint not in filled]
    partial = {h: found[h][1] for h in filled if found[h][1]}
    combined = part.model_copy(
        update={
            "fact_id": old.fact_id,
            "value": Decimal(total) / Decimal(slot.scale),
            "value_scaled": total,
            "derived_from": list(dict.fromkeys([*old.derived_from, *part.derived_from])),
            "terms": [*old.terms, *part.terms],
            "caution": part.caution,
        }
    )
    note = "earlier terms kept; added after slot search: " + ", ".join(
        f"{term.component} ({term.fact_id})" for term in terms
    )
    return _finish(combined, missing, _proxy_note(old.caution), partial, note), len(partial)


def _complete(
    slot: InputSlot, old: BoundInput | None, facts: list[VerifiedFact], basis: FactScope
) -> BoundInput | None:
    """The better binding for one derived slot, or None to keep what is there."""
    index = {fact.fact_id: fact for fact in facts}
    pool = [fact for fact in facts if out_of_basis_reason(fact, basis) is None]
    year = latest_money_year(facts)
    found = {hint: component_terms(slot, hint, pool, year) for hint in slot.derive_from}
    candidates: list[tuple[BoundInput, int]] = [(old, 0)] if old is not None else []
    if old is not None and old.missing:
        merged = _merged(slot, old, found, index, basis)
        candidates += [merged] if merged else []
    scratch = _from_scratch(slot, found, index, basis)
    if scratch and (old is not None or not scratch[0].missing):
        candidates.append(scratch)
    if not candidates:
        return None
    best = min(candidates, key=lambda pair: _rank(*pair))[0]
    return None if best is old else best


def needs_completion(item: BoundInput | None) -> bool:
    """True for a derived slot that is unbound, misses components or rests on a proxy."""
    return item is None or bool(item.missing) or _PROXY in item.caution


def complete_derived_slots(
    specs: list[ScoreSpec], binding: BindingResult, facts: list[VerifiedFact]
) -> BindingResult:
    """Rebind every incomplete derived slot from the current facts when that covers more of it."""
    result = copy.deepcopy(binding)
    for spec, slot in score_input_slots(specs):
        if not slot.derive_from or slot.mapping or slot.judge is not None:
            continue
        items = result.bound.setdefault(spec.score_id, [])
        old = next((item for item in items if item.slot == slot.slot), None)
        if not needs_completion(old):
            continue
        better = _complete(slot, old, facts, result.basis)
        if better is None:
            continue
        better = better.model_copy(update={"slot": slot.slot})
        result.bound[spec.score_id] = [
            *(item for item in items if item.slot != slot.slot),
            better,
        ]
        result.unbound.pop((spec.score_id, slot.slot), None)
    return result
