"""Bind every score input slot to a verified fact, with the LLM proposing and code checking.

The LLM sees the slot descriptions and a compact list of facts (id, statement, numbers) and
returns a `BindingOutput`. Code then keeps a binding only if the fact id exists, the claimed
value really is one of that fact's numbers, and the value converts exactly to the slot's
integer scale (`scaling.to_scaled_int`, using the unit recorded on the fact, not the LLM's).
Slots that are another score's output (for example the Internal Risk Grade's
`financial_strength_score`) are never bound to facts; the generator wires them to Lean.
Unbound slots are left out and make their score `not_computable` downstream.

A slot whose description defines it as a combination of other quantities (net debt = borrowings
less cash and liquid investments) may be bound as signed `terms`, each a number of a verified
fact; code sums the exactly scaled terms, so the derived value is still never LLM arithmetic.
Values are matched tolerantly (thousands separators, currency marks, trailing zeros), and a
value the fact's statement itself contains is accepted even when the extractor missed it in
`numbers` (its unit is then read from the words after the number in the statement, never from
the LLM); a number recorded without a money unit likewise takes the unit the statement writes
after it ("1,234.56 INR lakh"). Terms in different units are each converted to the slot's unit
before they are summed (the prompt says so, so the model never refuses a mixed-unit sum), and a
cash-flow component (interest paid, repayments, also when loosely named) or a term whose fact
states an outflow enters with its absolute figure, the sign coming only from the term's sign
(`components.unsigned_term`). The latest audited year is the latest year with at least a quarter as
many money figures as the most frequent year (an old offer document in the pack can state more
figures for its own year than the current annual report does). Each term of a derived slot is
checked by `components.outlier_reason`: a figure over 20 times larger or smaller than the same
line item on the other basis in the same year, or in an adjacent year, adds an "implausible
figure" caution. `item_figure` reads a row's current-year figure for `complete_derived.py`:
dates and years between the row label and the figure are skipped, figure-free asides in
brackets are dropped, a "current" row never matches "non-current", a total never matches one
side of it, a row never matches the text after "other than", and a repayment row never matches
short-term borrowings.

The first prompt shows, per slot, only its best candidate facts (rarity-weighted word overlap
with the slot, at most `_FIRST_CANDIDATES`), not all facts; slots with no candidate are not
sent at all. A fact that carries a structured `record` is scored on its metric label alone
(the slot's words against `record.metric`), not on the whole templated sentence. Slots the
first reply leaves unbound or rejects get one retry listing the
rejection reason and the next-best candidates. Every slot still unbound at the end gets a
human-readable reason in `BindingResult.unbound`.

Derived slots show a plain-language meaning per component (`components.py`); each term names its
component and every component is a term or listed in `missing`, else the binding is rejected. A
liquid-investment term whose fact sits under non-current assets is rejected, and so is any fact
whose scope differs from the run's basis (consolidated when consolidated statements exist, else
standalone); both rejections feed the single retry. A missing component or a proxy term sets
`BoundInput.caution`, which makes a passing rule `caution` (`rules.py`).

A slot with a `run_parameter` whose bank-supplied fact exists is bound first, in code
(`bank_binding.py`), and never shown to the model. A slot the model's batched reply leaves out
entirely (no entry in `bindings`, unlike an explicit null answer) is asked again in batches of
at most `_REASK_BATCH` with the same prompt shape restricted to those slots and their candidates.

Three kinds of slot are not bound by the fact-picking prompt. A slot with a `mapping` (the
external rating index) is bound by `bind_rating` from the grade a fact states, and only if no
fact does is the model asked (`judge_slot`). A slot with `judge` settings (default flag, major
red-flag count) is judged by one `policy.judge_slot` call against the policy rubric. A slot
with a `definition` shows it in the prompt together with its `derive_from` hints, whose
candidate facts are added to its own, and a worked example teaches the model to answer with
signed `terms`. Finally a still-unbound slot with a `fallback_slot` takes that slot's fact
(projected turnover falls back to the latest revenue) with the slot's `fallback_note` recorded
on the binding, so the substitution is visible in the Lean file and the report.

A slot with `derive_from` hints that is still unbound after the retry gets a deterministic
derivation (`derive_deterministically`): a fact with a `record` is read first, the hint phrase
matched against `record.metric` and the figure and its year taken from `record.value` and
`record.period` without parsing the sentence; otherwise each hint phrase is matched against the
fact statements by distinctive words (generic words like "paid" or "scheduled" ignored), and the
best fact of the latest period that states exactly one money figure for the year (or a
"<this year>, compared to <last year>" pair, taking the first) supplies the term. The sign is -
when the slot's `definition` puts "minus" or "less" just before the hint, else +. Only if every
hint binds is the slot bound, with the note "derived deterministically from <hints>"; a tie
between facts with different figures, or any hint without a fact, leaves the slot unbound.
The retry prompt for such slots lists the candidates of each component and insists on `terms`.

A plain slot the policy reads from one statement row (`components.SLOT_ROWS`: gross finance cost,
EBITDA) is bound by code, not by the model's pick, whenever a fact of the basis states such a
row (`statement_row_binding`): only facts of the slot's statement count (no cash flow for a
profit and loss item), the row must open the fact's label (after basis words, "total" or
"less"), and the figure must be for the latest year. The best tier wins, then an exact label,
then the lowest fact id, so two runs over the same facts bind the same fact; a later tier is a
stand-in and carries a proxy caution. Without such a row the model's pick stands, unless it is a
fact of the wrong statement. A proxy caution is only ever set by code (`term_proxy_reason`, a
stand-in row); the model's note is kept as the binding note. A fact's row label is its
statement up to the verb, or up to a trailing "as at ..." or "for <Company> Limited" the
extractor may put before the verb, so "total non-current assets for Craftsman Automation
Limited as at March 31, 2026 was ..." is labelled "total non-current assets".
"""

import asyncio
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, field_validator

from busybee.llm import Message, Provider, Role, StructuredOutputError, complete_as
from busybee.policy.bank_binding import bank_input_binding
from busybee.policy.bind_rating import rating_binding
from busybee.policy.components import (
    component_lines,
    is_cash_flow_component,
    is_flow_fact,
    item_wordings,
    normalise_component,
    out_of_basis_reason,
    outlier_reason,
    reporting_basis,
    slot_rows,
    statement_fits,
    term_proxy_reason,
    uncovered_components,
    unsigned_term,
    wrong_section_reason,
)
from busybee.policy.judge_slot import judge_slot
from busybee.policy.policy_sections import PolicySection
from busybee.policy.scaling import ScalingError, to_scaled_int
from busybee.schema.facts import FactScope, NumericValue, VerifiedFact
from busybee.schema.policy import BoundInput, BoundTerm, InputSlot, ScoreSpec

BIND_TASK = "policy.bind_inputs"

_SYSTEM = (
    "You bind the input slots of bank credit scores to verified facts from a borrower's "
    "documents. For each slot choose the single fact whose number is exactly what the slot "
    "describes (right metric, right period: use the latest audited year unless the slot says "
    "otherwise). Copy the number's value and unit from that fact's numbers list unchanged. "
    "If no fact fits, set fact_id and value to null. Never invent or compute a number. "
    "Only when a slot's description defines it as a combination of other quantities (for "
    "example borrowings less cash and liquid investments) and no single fact states it, leave "
    "fact_id and value null and list the pieces in terms: each term names a fact, copies one "
    "of its numbers unchanged, and has sign 1 (add) or -1 (subtract). Terms may be in "
    "different units (lakh, crore, million): copy each term's own value and unit; code "
    "converts every term to the slot's unit before summing, so a unit difference is never a "
    "reason to leave a slot unbound or to call a term a proxy. A slot may show a "
    "definition and derive_from hints: follow the definition exactly (same period for every "
    "term, latest audited year unless stated) and use the hinted quantities as terms. Each "
    "listed component has a plain-language meaning: obey it, and set every term's component "
    "to the component name exactly as listed. Every component must appear as a term or by "
    "name in missing (a list of components no fact supports); never fill a component with a "
    "figure its meaning excludes, and never mix consolidated and standalone facts in one "
    "slot. A fact "
    "starting 'Bank input:' is a figure the bank supplied for exactly that quantity; use it "
    "for the matching slot. Worked example: slot cfads is defined as EBITDA less cash taxes "
    "paid and no fact states it; F010 says EBITDA was INR 420.00 crore and F044 says cash "
    "taxes paid were INR 36.50 crore, so answer "
    '{"score_id": "s", "slot": "cfads", "fact_id": null, "value": null, "terms": '
    '[{"fact_id": "F010", "component": "ebitda", "value": 420.00, "unit": "INR crore", '
    '"sign": 1}, {"fact_id": "F044", "component": "cash taxes paid", "value": 36.50, '
    '"unit": "INR crore", "sign": -1}], "missing": [], "note": ""}. '
    "In note write one short line, only when a term is a proxy for what the definition names "
    "(for example a tax charge where the definition says tax paid); otherwise leave it empty."
)
_RETRY_NOTE = (
    "These slots were left unbound or rejected in a first pass. For each, the reason and the "
    "facts sharing the most words with the slot are listed. Choose again only if one of the "
    "listed facts (or a combination of them, via terms) truly gives the slot's quantity; "
    "otherwise keep fact_id and value null."
)
_MIN_WORD = 4
_FIRST_CANDIDATES = 15
_RETRY_CANDIDATES = 15
_REASK_BATCH = 3
_HINT_CANDIDATES = 5
_NOTE_CHARS = 300
_GENERIC_WORDS = frozenset(
    "paid scheduled latest audited year years end ended full during period previous "
    "company stated values value amount number and the for with less from that this".split()
)
_MONEY_UNITS = ("inr", "lakh", "crore", "million", "billion", "thousand")
_COMPARISON = re.compile(r"\b(compared (?:to|with)|from|versus|vs\.?)\b", re.IGNORECASE)
_NEGATIVE_LEAD = re.compile(r"(?:minus|less|-)\s*$", re.IGNORECASE)
_STATEMENT_NUMBER = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?")
_UNIT_AFTER = re.compile(
    r"\)?\s*(?:(?:INR|Rs\.?|₹)\s*)?"
    r"(lakhs?|lacs?|crores?|cr\b|million|mn\b|billion|bn\b|thousand|%|per cent|x\b|times)",
    re.IGNORECASE,
)


def _parse_decimal(raw: object) -> Decimal | None:
    """Parse a number the model wrote loosely: separators, currency marks, units."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    text = re.sub(r"[,\s_]|INR|Rs\.?|₹|crore|cr\b", "", str(raw), flags=re.IGNORECASE)
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class Term(BaseModel):
    """One signed number of a verified fact in a derived slot."""

    fact_id: str
    value: Decimal
    unit: str = ""
    sign: int = 1
    component: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _loose_value(cls, raw: object) -> object:
        parsed = _parse_decimal(raw)
        return raw if parsed is None else parsed


class SlotBinding(BaseModel):
    """The LLM's proposed fact and value for one slot of one score."""

    score_id: str
    slot: str
    fact_id: str | None = None
    value: Decimal | None = None
    unit: str = ""
    period: str = ""
    terms: list[Term] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    note: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _loose_value(cls, raw: object) -> object:
        if raw is None or raw == "":
            return None
        parsed = _parse_decimal(raw)
        return raw if parsed is None else parsed


class BindingOutput(BaseModel):
    """All slot bindings proposed by the LLM."""

    bindings: list[SlotBinding] = Field(default_factory=list)


@dataclass
class BindingResult:
    """Validated bindings per score id, proposal rejections, and why each slot stayed unbound."""

    bound: dict[str, list[BoundInput]] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)
    unbound: dict[tuple[str, str], str] = field(default_factory=dict)
    basis: FactScope = FactScope.standalone


def score_input_slots(specs: list[ScoreSpec]) -> list[tuple[ScoreSpec, InputSlot]]:
    """Return every (score, slot) pair whose value must come from a fact."""
    score_ids = {spec.score_id for spec in specs}
    return [
        (spec, slot)
        for spec in specs
        for slot in spec.inputs
        if slot.slot not in score_ids or slot.slot == spec.score_id
    ]


def _slots_text(pairs: list[tuple[ScoreSpec, InputSlot]]) -> str:
    lines = []
    for spec, slot in pairs:
        lines.append(
            f"- score_id={spec.score_id} slot={slot.slot} unit={slot.unit!r}: {slot.description}"
        )
        if slot.definition:
            lines.append(f"    definition: {slot.definition}")
        if slot.derive_from:
            lines.append(f"    derive_from: {'; '.join(slot.derive_from)}")
            lines.extend(component_lines(slot))
    return "\n".join(lines)


def _facts_text(facts: list[VerifiedFact]) -> str:
    lines = []
    for fact in facts:
        numbers = "; ".join(
            f"{n.label}={n.value} {n.unit} {n.period}".strip() for n in fact.numbers
        )
        section = getattr(fact.record, "section", None) if fact.record is not None else None
        where = f" | section: {section}" if section else ""
        lines.append(f"{fact.fact_id}: {fact.statement}{where} | numbers: {numbers or 'none'}")
    return "\n".join(lines)


def binding_messages(
    pairs: list[tuple[ScoreSpec, InputSlot]],
    facts: list[VerifiedFact],
    retry_notes: dict[tuple[str, str], str] | None = None,
    candidates: dict[tuple[str, str], list[VerifiedFact]] | None = None,
) -> list[Message]:
    """Build the prompt: slot descriptions, per-slot candidate ids, and the facts they name."""
    numeric = [fact for fact in facts if _has_figures(fact)]
    if retry_notes:
        notes = "\n".join(
            f"- {score_id}.{slot}: {note}" for (score_id, slot), note in retry_notes.items()
        )
        content = (
            f"{_RETRY_NOTE}\n\nSlots to bind:\n{_slots_text(pairs)}\n\n"
            f"Reasons and candidate facts:\n{notes}\n\n"
            f"Candidate facts:\n{_facts_text(numeric)}\n\nReturn one binding per slot above."
        )
    else:
        per_slot = "\n".join(
            f"- {score_id}.{slot}: {', '.join(fact.fact_id for fact in found)}"
            for (score_id, slot), found in (candidates or {}).items()
        )
        shown = (
            f"Candidate fact ids per slot (choose from these):\n{per_slot}\n\n" if per_slot else ""
        )
        content = (
            f"Slots to bind:\n{_slots_text(pairs)}\n\n{shown}"
            f"Verified facts:\n{_facts_text(numeric)}\n\n"
            "Return one binding per slot listed above."
        )
    return [Message(role=Role.system, content=_SYSTEM), Message(role=Role.user, content=content)]


def _has_figures(fact: VerifiedFact) -> bool:
    return bool(fact.numbers) or bool(re.search(r"\d", fact.statement))


def _same_value(left: Decimal, right: Decimal) -> bool:
    return left == right or abs(left - right) <= Decimal("0.0001") * max(abs(right), Decimal(1))


def _matching_number(
    fact: VerifiedFact, value: Decimal | None, unit: str = ""
) -> NumericValue | None:
    """Return the fact number equal to value (trailing zeros aside), preferring a unit match."""
    matches = [n for n in fact.numbers if value is not None and _same_value(n.value, value)]
    for number in matches:
        if number.unit.strip().lower() == unit.strip().lower():
            return _with_statement_unit(fact, number)
    return _with_statement_unit(fact, matches[0]) if matches else _number_in_statement(fact, value)


def _with_statement_unit(fact: VerifiedFact, number: NumericValue) -> NumericValue:
    """A number recorded without a money unit takes the one the statement writes after it."""
    if any(word in number.unit.lower() for word in _MONEY_UNITS if word != "inr"):
        return number
    stated = _number_in_statement(fact, abs(number.value))
    if stated is None or stated.unit in ("", "%", "x", "times"):
        return number
    return number.model_copy(update={"unit": f"INR {stated.unit}"})


def _number_in_statement(fact: VerifiedFact, value: Decimal | None) -> NumericValue | None:
    """Find value written in the statement itself, taking its unit from the words after it."""
    if value is None:
        return None
    for match in _STATEMENT_NUMBER.finditer(fact.statement):
        raw = match.group(0).lstrip("(").replace(",", "")
        try:
            found = Decimal(raw)
        except InvalidOperation:
            continue
        if not _same_value(found, value):
            continue
        tail = _UNIT_AFTER.match(fact.statement, match.end())
        unit = tail.group(1).lower().rstrip("s") if tail else ""
        unit = {"lac": "lakh", "cr": "crore", "mn": "million", "bn": "billion"}.get(unit, unit)
        return NumericValue(
            label="statement", value=found, unit="%" if unit == "per cent" else unit
        )
    return None


def _bind_single(
    binding: SlotBinding, slot: InputSlot, fact: VerifiedFact, basis: FactScope
) -> BoundInput | str:
    mixed = out_of_basis_reason(fact, basis)
    if mixed:
        return mixed
    number = _matching_number(fact, binding.value, binding.unit)
    if number is None:
        return f"value {binding.value} is not a number of {binding.fact_id}"
    try:
        scaled = to_scaled_int(number.value, number.unit, slot)
    except ScalingError as error:
        return str(error)
    return BoundInput(
        slot=binding.slot,
        fact_id=fact.fact_id,
        value=number.value,
        unit=number.unit,
        value_scaled=scaled,
        note=" ".join(binding.note.split())[:_NOTE_CHARS],
    )


def _proxy_caution(note: str) -> str:
    text = " ".join(note.split())[:_NOTE_CHARS]
    return f"proxy used: {text}" if text else ""


def _bind_derived(
    binding: SlotBinding,
    slot: InputSlot,
    facts: dict[str, VerifiedFact],
    basis: FactScope,
    fixed: dict[str, int] | None = None,
) -> BoundInput | str:
    total = 0
    outliers: list[str] = []
    proxies: list[str] = []
    bound_terms: list[BoundTerm] = []
    fixed = fixed or {}
    uncovered = uncovered_components(
        slot, [term.component for term in binding.terms], binding.missing
    )
    if uncovered:
        return f"components neither used as a term nor listed as missing: {', '.join(uncovered)}"
    for term in binding.terms:
        fact = facts.get(term.fact_id)
        if fact is None:
            return f"unknown fact {term.fact_id} in terms"
        mixed = out_of_basis_reason(fact, basis)
        if mixed:
            return f"term {term.fact_id}: {mixed}"
        wrong = wrong_section_reason(term.component, fact)
        if wrong:
            return f"term {term.fact_id}: {wrong}"
        if term.sign not in (1, -1):
            return f"term sign {term.sign} must be 1 or -1"
        if term.component in fixed:
            total += term.sign * fixed[term.component]
            bound_terms.append(_bound_term(term, term.value, term.unit, fixed[term.component]))
            continue
        number = _matching_number(fact, term.value, term.unit)
        if number is None:
            return f"term value {term.value} is not a number of {term.fact_id}"
        value = abs(number.value) if unsigned_term(term.component, fact) else number.value
        try:
            scaled = to_scaled_int(value, number.unit, slot)
        except ScalingError as error:
            return f"term {term.fact_id}: {error}"
        total += term.sign * scaled
        bound_terms.append(_bound_term(term, number.value, number.unit, scaled))
        outlier = outlier_reason(term.component, fact, number, facts.values())
        if outlier:
            outliers.append(f"implausible figure: {outlier}")
        proxy = term_proxy_reason(slot, term.component, fact)
        if proxy:
            proxies.append(proxy)
    first = binding.terms[0]
    caution = derived_caution(binding.missing, "; ".join(dict.fromkeys(proxies)), outliers)
    note = " ".join(binding.note.split())[:_NOTE_CHARS]
    return BoundInput(
        slot=binding.slot,
        fact_id=first.fact_id,
        value=Decimal(total) / Decimal(slot.scale),
        unit=slot.unit,
        value_scaled=total,
        derived_from=list(dict.fromkeys(term.fact_id for term in binding.terms)),
        note="; ".join(part for part in (note, caution if binding.missing else "") if part),
        caution=caution,
        missing=list(binding.missing),
        terms=bound_terms,
    )


def _bound_term(term: Term, value: Decimal, unit: str, scaled: int) -> BoundTerm:
    return BoundTerm(
        component=term.component,
        fact_id=term.fact_id,
        value=value,
        unit=unit,
        sign=term.sign,
        value_scaled=scaled,
    )


def bind_terms(
    slot: InputSlot,
    terms: list[Term],
    missing: list[str],
    note: str,
    facts: dict[str, VerifiedFact],
    basis: FactScope,
    fixed: dict[str, int] | None = None,
) -> BoundInput | str:
    """Validate and sum signed terms for a derived slot exactly as a model answer would be.

    A component in `fixed` is another slot's binding: its term adds that scaled value as it is,
    without the scaling, outlier and proxy checks the slot binding already went through.
    """
    binding = SlotBinding(score_id="", slot=slot.slot, terms=terms, missing=missing, note=note)
    return _bind_derived(binding, slot, facts, basis, fixed)


def derived_caution(missing: list[str], proxy: str, extra: list[str] | None = None) -> str:
    """The caution of a derived binding: missing components, code-found proxies, outliers."""
    cautions = []
    if missing:
        cautions.append(f"missing component(s): {', '.join(missing)}; value computed without them")
    if proxy.strip():
        cautions.append(_proxy_caution(proxy))
    return "; ".join([*cautions, *(extra or [])])


def validate_bindings(
    output: BindingOutput,
    specs: list[ScoreSpec],
    facts: dict[str, VerifiedFact],
    basis: FactScope | None = None,
) -> BindingResult:
    """Keep only bindings that name a real fact of the run's basis, a real number, exact scale."""
    basis = basis or reporting_basis(facts.values())
    slots = {
        (spec.score_id, slot.slot): slot
        for spec, slot in score_input_slots(specs)
        if not _is_special(slot)
    }
    result = BindingResult(bound={spec.score_id: [] for spec in specs}, basis=basis)
    seen: set[tuple[str, str]] = set()
    for binding in output.bindings:
        key = (binding.score_id, binding.slot)
        label = f"{binding.score_id}.{binding.slot}"
        slot = slots.get(key)
        outcome: BoundInput | str
        if slot is None:
            result.rejected.append(f"{label}: unknown or non-fact slot")
            continue
        if key in seen:
            result.rejected.append(f"{label}: duplicate binding")
            continue
        if binding.terms and binding.fact_id is None:
            outcome = _bind_derived(binding, slot, facts, basis)
        elif binding.fact_id is None or binding.value is None:
            result.rejected.append(f"{label}: no fact chosen")
            continue
        elif binding.fact_id not in facts:
            outcome = f"unknown fact {binding.fact_id}"
        else:
            outcome = _bind_single(binding, slot, facts[binding.fact_id], basis)
        if isinstance(outcome, str):
            result.rejected.append(f"{label}: {outcome}")
            continue
        seen.add(key)
        result.bound[binding.score_id].append(outcome)
    return result


_SYNONYMS = {
    "borrowing": "debt",
    "loan": "debt",
    "finance": "interest",
    "worth": "equity",
    "turnover": "revenue",
    "sale": "revenue",
}


def _stem(word: str) -> str:
    stem = word[:-1] if len(word) > _MIN_WORD and word.endswith("s") else word
    return _SYNONYMS.get(stem, stem)


def _words_of(text: str, min_len: int = _MIN_WORD) -> set[str]:
    words = (_stem(word) for word in re.findall(r"[a-z]+", text.lower()) if len(word) >= min_len)
    return {word for word in words if word not in _GENERIC_WORDS}


def _fact_words(fact: VerifiedFact, min_len: int = _MIN_WORD) -> set[str]:
    """Words a fact is scored on: its record's metric label, else its whole statement."""
    return _words_of(fact.record.metric if fact.record else fact.statement, min_len)


def _word_weights(facts: list[VerifiedFact]) -> dict[str, float]:
    """Rarity weight of each word over the fact statements, so common words count little."""
    document_frequency = Counter(word for fact in facts for word in _fact_words(fact, 3))
    return {
        word: math.log((1 + len(facts)) / (1 + count)) + 0.1
        for word, count in document_frequency.items()
    }


def candidate_facts(
    slot: InputSlot,
    facts: list[VerifiedFact],
    *,
    limit: int = _FIRST_CANDIDATES,
    skip: set[str] | None = None,
    weights: dict[str, float] | None = None,
) -> list[VerifiedFact]:
    """Facts with figures sharing the rarest words with the slot, best first, at most limit."""
    weights = weights or _word_weights(facts)
    name_words = _words_of(slot.slot.replace("_", " "), min_len=3)
    wanted = name_words | _words_of(slot.description, min_len=3)
    wanted |= _words_of(slot.definition, min_len=3)
    scored = []
    for fact in facts:
        if not _has_figures(fact) or fact.fact_id in (skip or set()):
            continue
        shared = wanted & _fact_words(fact, 3)
        score = sum(weights.get(word, 0.1) * (3 if word in name_words else 1) for word in shared)
        if name_words and name_words <= shared:
            score += 3 * sum(weights.get(word, 0.1) for word in name_words)
        if shared:
            scored.append((score, fact))
    scored.sort(key=lambda item: -item[0])
    return [fact for _, fact in scored[:limit]]


def slot_candidates(
    slot: InputSlot,
    facts: list[VerifiedFact],
    *,
    limit: int = _FIRST_CANDIDATES,
    skip: set[str] | None = None,
    weights: dict[str, float] | None = None,
) -> list[VerifiedFact]:
    """The slot's own best facts plus a few per `derive_from` hint, without repeats."""
    weights = weights or _word_weights(facts)
    found = candidate_facts(slot, facts, limit=limit, skip=skip, weights=weights)
    seen = {fact.fact_id for fact in found} | (skip or set())
    for hint in slot.derive_from:
        pseudo = InputSlot(slot=hint.replace("_", " "))
        for fact in candidate_facts(
            pseudo, facts, limit=_HINT_CANDIDATES, skip=seen, weights=weights
        ):
            found.append(fact)
            seen.add(fact.fact_id)
    return found


def _money_numbers(fact: VerifiedFact) -> list[NumericValue]:
    return [n for n in fact.numbers if any(u in n.unit.lower() for u in _MONEY_UNITS)]


def _year_of(period: str) -> int:
    found = re.findall(r"(?:19|20)\d{2}", period)
    return int(found[-1]) if found else 0


_YEAR_TOKEN = re.compile(r"\b(?:(?:19|20)\d{2}|FY ?(\d{2}))\b")
_FIGURE_REACH = 70
_MIN_YEAR_FIGURES = 3
_YEAR_SHARE = 0.25
_LABEL_TAIL = 25
_NOT_ANNUAL = re.compile(
    r"\bQ[1-4]\b|quarter|\bH[12]\b|half[- ]year|mark-to-market|expect|project|estimat|forecast",
    re.IGNORECASE,
)


def _year_after(statement: str, number: NumericValue) -> int:
    """The year written right after the number in the statement, before the next figure."""
    for match in _STATEMENT_NUMBER.finditer(statement):
        try:
            found = Decimal(match.group(0).lstrip("(").replace(",", ""))
        except InvalidOperation:
            continue
        if _same_value(found, number.value):
            window = statement[match.end() : match.end() + _FIGURE_REACH]
            stop = _STATEMENT_NUMBER.search(window)
            token = _YEAR_TOKEN.search(window[: stop.start()] if stop else window)
            if token is None:
                return 0
            return 2000 + int(token.group(1)) if token.group(1) else int(token.group(0))
    return 0


def _period_year(period: str) -> int:
    """Closing year of a period: FY2024-25, FY24-25 and FY25 give 2025, "31 March 2025" 2025."""
    span = re.search(
        r"(?:\b(?:FY|CY)\s?'?(?:\d{4}|\d{2})|\b20\d{2})\s?[-/–]\s?(\d{2,4})\b", period, re.I
    )
    if span:
        end = int(span.group(1))
        return end if end > 99 else 2000 + end
    short = re.search(r"\b(?:FY|CY)\s?'?(\d{2})\b", period, re.IGNORECASE)
    return 2000 + int(short.group(1)) if short else _year_of(period)


def _figure_year(fact: VerifiedFact, number: NumericValue) -> int:
    if fact.record is not None:
        return _period_year(number.period)
    return _year_after(fact.statement, number) or _year_of(number.period)


def _current_figure(fact: VerifiedFact) -> NumericValue | None:
    """The one money figure for the latest year: the only one, or the later of a stated pair."""
    money = _money_numbers(fact)
    if fact.record is not None:
        return money[0] if money and money[0].value == fact.record.value else None
    if len(money) == 1:
        return money[0]
    if len(money) == 2 and _COMPARISON.search(fact.statement):
        first, second = (_figure_year(fact, n) for n in money)
        return money[1] if second > first else money[0]
    return None


_EQUIVALENT = {
    "paid": ("paid", "payment", "expense", "cost", "charge"),
    "principal": ("principal", "repayment", "repay"),
    "repayment": ("principal", "repayment", "repay"),
}
_PHRASE_GAP = r"(?:\W+\w+){0,2}?\W+"


def _phrase_pattern(hint: str) -> re.Pattern[str] | None:
    """A regex for the hint's distinctive words in order, each allowing its equivalents."""
    groups: list[tuple[str, ...]] = []
    for raw in re.findall(r"[a-z]+", hint.lower()):
        word = raw if raw in _EQUIVALENT or raw in _GENERIC_WORDS else raw.removesuffix("s")
        word = "repayment" if word == "repayments" else word
        if len(word) < _MIN_WORD - 1 or (word in _GENERIC_WORDS and word not in _EQUIVALENT):
            continue
        group = tuple(sorted(_EQUIVALENT.get(word, (word.removesuffix("s"),))))
        if group not in groups:
            groups.append(group)
    if not groups:
        return None
    parts = ["(?:" + "|".join(rf"{w}\w*" for w in group) + ")" for group in groups]
    return re.compile(rf"(?<!\w){_PHRASE_GAP.join(parts)}", re.IGNORECASE)


_MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
)
_DATE = re.compile(
    rf"\b(?:{_MONTH_NAMES})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_NAMES})\.?,?\s+\d{{4}}"
    r"|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
    r"|\b(?:FY\s?)?(?:19|20)\d{2}(?:\s?[-–/]\s?\d{2,4})?\b",
    re.IGNORECASE,
)
_SIDE_BEFORE = re.compile(r"(?:non[- ]?current|current|short[- ]?term|long[- ]?term)[\s-]*$", re.I)
_NON_BEFORE = re.compile(r"non[- ]?$", re.IGNORECASE)
_SHORT_TERM = re.compile(r"short[- ]?term|current borrowing", re.IGNORECASE)
_SIDED_FIRST = frozenset({"current", "non", "short", "long"})
_OTHER_THAN = re.compile(r"other\s+than\s*$", re.IGNORECASE)
_ASIDE = re.compile(r"\s*\((?:[^()\d]|\([^()\d]*\))*\)")


def _without_dates(text: str) -> str:
    """The text with every date and year blanked out, keeping its length."""
    return _DATE.sub(lambda match: " " * len(match.group(0)), text)


def _side_fits(text: str, match: re.Match[str], wording: str) -> bool:
    """False when the matched row is another side of the item than the wording asks for."""
    before = text[max(0, match.start() - 14) : match.start()]
    words = re.findall(r"[a-z]+", wording.lower())
    first = words[0] if words else ""
    if first == "current" and _NON_BEFORE.search(before):
        return False
    if _OTHER_THAN.search(before):
        return False
    if first not in _SIDED_FIRST and _SIDE_BEFORE.search(before):
        return False
    label = text[match.start() : match.end() + _LABEL_TAIL]
    return not ("repay" in wording.lower() and _SHORT_TERM.search(label))


def _states_figure_after(
    fact: VerifiedFact, pattern: re.Pattern[str], wording: str = ""
) -> NumericValue | None:
    """The fact's current money figure when the statement writes it right after the phrase."""
    if fact.record is not None:
        record = fact.record
        context = f"{record.metric} {record.period} {record.qualifier or ''}"
        found = pattern.search(record.metric)
        if _NOT_ANNUAL.search(context) or found is None:
            return None
        if wording and not _side_fits(record.metric, found, wording):
            return None
        return _current_figure(fact)
    figure = None if _NOT_ANNUAL.search(fact.statement) else _current_figure(fact)
    plain = _without_dates(fact.statement)
    for phrase in pattern.finditer(fact.statement):
        if wording and not _side_fits(fact.statement, phrase, wording):
            continue
        window = " ".join(plain[phrase.end() :].split())[:_FIGURE_REACH]
        for match in _STATEMENT_NUMBER.finditer(window):
            try:
                found = Decimal(match.group(0).lstrip("(").replace(",", ""))
            except InvalidOperation:
                continue
            if figure is not None and any(
                _same_value(abs(found), abs(n.value)) for n in _money_numbers(fact)
            ):
                return figure
            break
    return None


def _component_pool(
    hint: str, facts: list[VerifiedFact], weights: dict[str, float], limit: int
) -> list[VerifiedFact]:
    """Facts that state a money figure right after the hint phrase, best first."""
    pattern = _phrase_pattern(hint)
    if pattern is None:
        return []
    found = candidate_facts(
        InputSlot(slot=hint.replace("_", " ")), facts, limit=len(facts), weights=weights
    )
    return [f for f in found if _states_figure_after(f, pattern) is not None][:limit]


def component_candidates(
    slot: InputSlot, facts: list[VerifiedFact], weights: dict[str, float]
) -> dict[str, list[VerifiedFact]]:
    """For a slot with `derive_from` hints, the best fact ids per hint phrase."""
    if not slot.derive_from:
        return {}
    return {
        hint: _component_pool(hint, facts, weights, _HINT_CANDIDATES) for hint in slot.derive_from
    }


def _component_lines(parts: dict[str, list[VerifiedFact]]) -> str:
    lines = [
        f"    component '{hint}': "
        + (", ".join(fact.fact_id for fact in found) if found else "no candidate fact")
        for hint, found in parts.items()
    ]
    return (
        "\n".join(lines)
        + "\n    This slot is a combination: leave fact_id and value null and answer with "
        "`terms`, one signed term per component, copying each number unchanged."
    )


def _term_sign(slot: InputSlot, hint: str) -> int:
    at = slot.definition.lower().find(hint.lower())
    return -1 if at > 0 and _NEGATIVE_LEAD.search(slot.definition[:at]) else 1


def _reference_year(facts: list[VerifiedFact]) -> int:
    """The latest audited year: the latest year with a fair share of the pack's money figures."""
    years = Counter(
        year
        for f in facts
        if not _NOT_ANNUAL.search(f.statement)
        for n in _money_numbers(f)
        if (year := _figure_year(f, n))
    )
    if not years:
        return 0
    top = years.most_common(1)[0][1]
    floor = max(min(_MIN_YEAR_FIGURES, top), top * _YEAR_SHARE)
    return max(year for year, count in years.items() if count >= floor)


def _is_consolidated(fact: VerifiedFact) -> bool:
    return fact.scope == "consolidated" or bool(
        re.search(r"\b(?:consolidated|group)\b", fact.statement, re.IGNORECASE)
    )


def _component_term(
    hint: str, slot: InputSlot, facts: list[VerifiedFact], weights: dict[str, float]
) -> Term | None:
    year = _reference_year(facts)
    pattern = _phrase_pattern(hint)
    pool = _component_pool(hint, facts, weights, _RETRY_CANDIDATES)
    usable = [(fact, _states_figure_after(fact, pattern)) for fact in pool] if pattern else []
    usable = [(f, n) for f, n in usable if n is not None and _figure_year(f, n) == year]
    consolidated = [(f, n) for f, n in usable if _is_consolidated(f)]
    usable = consolidated or usable
    if not usable or len({n.value for _, n in usable}) > 1:
        return None
    fact, number = usable[0]
    return Term(
        fact_id=fact.fact_id,
        value=number.value,
        unit=number.unit,
        sign=_term_sign(slot, hint),
        component=hint,
    )


def derive_deterministically(
    slot: InputSlot,
    facts: list[VerifiedFact],
    weights: dict[str, float] | None = None,
    basis: FactScope | None = None,
) -> BoundInput | None:
    """Bind a `derive_from` slot from one fact per component, or None unless all components bind."""
    if not slot.derive_from:
        return None
    weights = weights or _word_weights(facts)
    terms = [_component_term(hint, slot, facts, weights) for hint in slot.derive_from]
    if any(term is None for term in terms):
        return None
    chosen = [term for term in terms if term is not None]
    note = "derived deterministically from " + "; ".join(
        f"{hint} ({term.fact_id})" for hint, term in zip(slot.derive_from, chosen, strict=True)
    )
    outcome = _bind_derived(
        SlotBinding(score_id="", slot=slot.slot, terms=chosen, note=note),
        slot,
        {fact.fact_id: fact for fact in facts},
        basis or reporting_basis(facts),
    )
    return None if isinstance(outcome, str) else outcome


def unresolved_components(slot: InputSlot, facts: list[VerifiedFact]) -> list[str]:
    """The `derive_from` hints for which no single current-year fact states a figure."""
    weights = _word_weights(facts)
    return [
        hint for hint in slot.derive_from if _component_term(hint, slot, facts, weights) is None
    ]


_SIDE_PREFIX = re.compile(r"^(?:non-current|current)\s+(?=.*(?:lease liabilit|borrowing))", re.I)


def line_item_stated(
    item: str, component: str, facts: list[VerifiedFact], basis: FactScope
) -> bool:
    """True when a fact of the basis states a current-year figure right after the line item.

    For a cash-flow component only a cash-flow fact counts: the tax expense of the profit and
    loss statement is not income tax paid.
    """
    flow = is_cash_flow_component(component)
    patterns = [
        (pattern, "" if loose != wording else wording)
        for wording in item_wordings(item)
        if (pattern := _phrase_pattern(loose := _SIDE_PREFIX.sub("", wording))) is not None
    ]
    if not patterns:
        return False
    scoped = [
        fact
        for fact in facts
        if out_of_basis_reason(fact, basis) is None
        and wrong_section_reason(component, fact) is None
        and (not flow or is_flow_fact(fact))
    ]
    year = _reference_year(facts)
    return any(
        (number := _states_figure_after(fact, pattern, wording)) is not None
        and _figure_year(fact, number) == year
        for fact in scoped
        for pattern, wording in patterns
    )


def item_figure(fact: VerifiedFact, wording: str, year: int) -> NumericValue | None:
    """The fact's money figure for `year` written right after the row wording, else None."""
    pattern = _phrase_pattern(wording)
    if pattern is None:
        return None
    fact = fact.model_copy(
        update={
            "statement": _ASIDE.sub("", fact.statement),
            "numbers": [_with_statement_unit(fact, number) for number in fact.numbers],
        }
    )
    number = _states_figure_after(fact, pattern, wording)
    if number is None or (year and _figure_year(fact, number) != year):
        return None
    return _with_statement_unit(fact, number)


def term_sign(slot: InputSlot, hint: str) -> int:
    """-1 when the slot's definition subtracts the component, else +1."""
    return _term_sign(slot, hint)


def latest_money_year(facts: list[VerifiedFact]) -> int:
    """The year most money figures are stated for (0 when none), the pack's latest audited year."""
    return _reference_year(facts)


_LEAD_WORDS = re.compile(
    r"^(?:\W*(?:consolidated|standalone|total|less|net|gross|the|group)\b)*\W*", re.IGNORECASE
)
_LABEL_END = re.compile(
    r"\s+(?:was|were|is|are|stood|amounted)\b|\s+as\s+(?:at|on|of)\b"
    r"|\s+(?:for|of)\s+(?-i:(?:[A-Z][\w&.'-]*\s+){1,6}(?:Limited|Ltd\b\.?))",
    re.IGNORECASE,
)


def _row_label(fact: VerifiedFact) -> str:
    """The row label of a fact: its record's metric, else the statement up to its verb."""
    text = fact.record.metric if fact.record is not None else _LABEL_END.split(fact.statement)[0]
    return text[_LEAD_WORDS.match(text).end() :]


def label_is(fact: VerifiedFact, wording: str) -> bool:
    """True when the fact's row label is exactly the wording, basis and 'total' words aside."""
    label = normalise_component(_LABEL_END.split(_row_label(fact))[0])
    wanted = normalise_component(wording[_LEAD_WORDS.match(wording).end() :])
    return bool(wanted) and label.rstrip("s") == wanted.rstrip("s")


def _opens_label(fact: VerifiedFact, wording: str) -> bool:
    pattern = _phrase_pattern(wording)
    return pattern is not None and pattern.match(_row_label(fact)) is not None


def _fact_order(fact: VerifiedFact) -> tuple[int, str]:
    digits = re.sub(r"\D", "", fact.fact_id)
    return (int(digits) if digits else 0, fact.fact_id)


def _row_candidate(
    slot: InputSlot, fact: VerifiedFact, tiers: tuple[tuple[str, ...], ...], year: int
) -> tuple[tuple[int, bool, tuple[int, str]], BoundInput, str] | None:
    """The fact's best row for the slot as (sort key, binding, row), else None."""
    for tier, rows in enumerate(tiers):
        for row in rows:
            if not _opens_label(fact, row):
                continue
            number = item_figure(fact, row, year)
            if number is None:
                continue
            try:
                scaled = to_scaled_int(number.value, number.unit, slot)
            except ScalingError:
                continue
            exact = normalise_component(_LABEL_END.split(_row_label(fact))[0]).rstrip("s") == (
                normalise_component(row).rstrip("s")
            )
            bound = BoundInput(
                slot=slot.slot,
                fact_id=fact.fact_id,
                value=number.value,
                unit=number.unit,
                value_scaled=scaled,
            )
            return (tier, not exact, _fact_order(fact)), bound, row
    return None


def statement_row_binding(
    slot: InputSlot, facts: list[VerifiedFact], basis: FactScope
) -> BoundInput | None:
    """Bind a slot read from one statement row from the best fact stating it, or None."""
    spec = slot_rows(slot)
    if spec is None:
        return None
    statement, tiers = spec
    year = _reference_year(facts)
    found = [
        candidate
        for fact in facts
        if out_of_basis_reason(fact, basis) is None and statement_fits(slot, fact)
        if (candidate := _row_candidate(slot, fact, tiers, year)) is not None
    ]
    if not found:
        return None
    key, bound, row = min(found, key=lambda item: item[0])
    note = f"chosen by code: the {row} row of the {statement} statement ({bound.fact_id})"
    caution = (
        f"proxy used: {bound.fact_id} is the {row} row, a stand-in for {tiers[0][0]}"
        if key[0]
        else ""
    )
    return bound.model_copy(update={"note": note, "caution": caution})


def _apply_statement_rows(
    pairs: list[tuple[ScoreSpec, InputSlot]],
    result: BindingResult,
    facts: list[VerifiedFact],
    index: dict[str, VerifiedFact],
) -> None:
    """Replace the model's pick by the code's row choice; drop a pick of the wrong statement."""
    for spec, slot in pairs:
        if slot_rows(slot) is None:
            continue
        label = f"{spec.score_id}.{slot.slot}"
        items = result.bound.setdefault(spec.score_id, [])
        chosen = statement_row_binding(slot, facts, result.basis)
        kept = [item for item in items if item.slot != slot.slot]
        picked = next((item for item in items if item.slot == slot.slot), None)
        if chosen is not None:
            result.bound[spec.score_id] = [*kept, chosen]
            result.rejected = [line for line in result.rejected if not line.startswith(label)]
        elif picked is not None and picked.fact_id in index:
            if not statement_fits(slot, index[picked.fact_id]):
                result.bound[spec.score_id] = kept
                result.rejected.append(
                    f"{label}: {picked.fact_id} is not a {slot_rows(slot)[0]} figure"
                )


def _rejected_reasons(result: BindingResult) -> dict[str, str]:
    return {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in result.rejected}


def _is_bound(result: BindingResult, score_id: str, slot: str) -> bool:
    return any(item.slot == slot for item in result.bound.get(score_id, []))


def _merge(first: BindingResult, second: BindingResult) -> BindingResult:
    merged = BindingResult(
        bound={key: list(items) for key, items in first.bound.items()}, basis=first.basis
    )
    for score_id, items in second.bound.items():
        have = {item.slot for item in merged.bound.setdefault(score_id, [])}
        merged.bound[score_id].extend(item for item in items if item.slot not in have)
    still = {f"{sid}.{item.slot}" for sid, items in merged.bound.items() for item in items}
    merged.rejected = [
        line for line in [*first.rejected, *second.rejected] if line.split(":", 1)[0] not in still
    ]
    return merged


def _unbound_reasons(
    pairs: list[tuple[ScoreSpec, InputSlot]],
    result: BindingResult,
    shown: dict[tuple[str, str], int],
    retried: set[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    """Say why each slot that ended unbound could not be bound."""
    rejected = _rejected_reasons(result)
    reasons = {}
    for spec, slot in pairs:
        key = (spec.score_id, slot.slot)
        if _is_bound(result, *key):
            continue
        count = shown.get(key, 0)
        if rejected.get(f"{key[0]}.{key[1]}", "no fact chosen") != "no fact chosen":
            reasons[key] = f"proposed binding rejected: {rejected[f'{key[0]}.{key[1]}']}"
        elif count == 0:
            reasons[key] = "no verified fact shares key words with this slot"
        else:
            tried = " (including a retry)" if key in retried else ""
            reasons[key] = f"the model found no fitting fact among {count} candidates{tried}"
    return reasons


async def _bind_from_facts(
    provider: Provider,
    pairs: list[tuple[ScoreSpec, InputSlot]],
    specs: list[ScoreSpec],
    facts: list[VerifiedFact],
    basis: FactScope,
) -> BindingResult:
    """Bind bank slots in code, then the rest from per-slot candidates; re-ask, retry once."""
    fixed = {
        (spec.score_id, slot.slot): bound
        for spec, slot in pairs
        if (bound := bank_input_binding(slot, facts)) is not None
    }
    pairs = [(spec, slot) for spec, slot in pairs if (spec.score_id, slot.slot) not in fixed]
    result = await _bind_model_slots(provider, pairs, specs, facts, basis)
    for (score_id, slot_name), bound in fixed.items():
        kept = [item for item in result.bound.get(score_id, []) if item.slot != slot_name]
        result.bound[score_id] = [*kept, bound]
    return result


async def _reask_omitted(
    provider: Provider,
    omitted: list[tuple[ScoreSpec, InputSlot]],
    specs: list[ScoreSpec],
    first: dict[tuple[str, str], list[VerifiedFact]],
    index: dict[str, VerifiedFact],
    basis: FactScope,
) -> BindingResult:
    """Ask again, in small batches, for slots the batched reply left out altogether."""

    async def ask(batch: list[tuple[ScoreSpec, InputSlot]]) -> BindingResult:
        found = {
            (spec.score_id, slot.slot): first[(spec.score_id, slot.slot)] for spec, slot in batch
        }
        pool = list({f.fact_id: f for group in found.values() for f in group}.values())
        output = await complete_as(
            provider,
            binding_messages(batch, pool, candidates=found),
            BindingOutput,
            task=BIND_TASK,
        )
        return validate_bindings(output, specs, index, basis)

    batches = [omitted[i : i + _REASK_BATCH] for i in range(0, len(omitted), _REASK_BATCH)]
    merged = BindingResult(bound={spec.score_id: [] for spec in specs}, basis=basis)
    for answer in await asyncio.gather(*(ask(batch) for batch in batches)):
        merged = _merge(merged, answer)
    return merged


async def _bind_model_slots(
    provider: Provider,
    pairs: list[tuple[ScoreSpec, InputSlot]],
    specs: list[ScoreSpec],
    facts: list[VerifiedFact],
    basis: FactScope,
) -> BindingResult:
    empty = BindingResult(bound={spec.score_id: [] for spec in specs}, basis=basis)
    if not pairs:
        return empty
    index = {fact.fact_id: fact for fact in facts}
    facts = [fact for fact in facts if out_of_basis_reason(fact, basis) is None]
    weights = _word_weights(facts)
    first = {
        (spec.score_id, slot.slot): slot_candidates(slot, facts, weights=weights)
        for spec, slot in pairs
    }
    shown = {key: len(found) for key, found in first.items()}
    sendable = [(spec, slot) for spec, slot in pairs if first[(spec.score_id, slot.slot)]]
    result = empty
    if sendable:
        pool = list({f.fact_id: f for key in first for f in first[key]}.values())
        output = await complete_as(
            provider,
            binding_messages(sendable, pool, candidates={k: v for k, v in first.items() if v}),
            BindingOutput,
            task=BIND_TASK,
        )
        result = validate_bindings(output, specs, index, basis)
        answered = {(item.score_id, item.slot) for item in output.bindings}
        omitted = [(s, sl) for s, sl in sendable if (s.score_id, sl.slot) not in answered]
        if omitted:
            result = _merge(
                result, await _reask_omitted(provider, omitted, specs, first, index, basis)
            )
    rejected = _rejected_reasons(result)
    notes: dict[tuple[str, str], str] = {}
    retry_found: dict[tuple[str, str], list[VerifiedFact]] = {}
    for spec, slot in pairs:
        key = (spec.score_id, slot.slot)
        if slot.derive_from and not _is_bound(result, *key):
            sendable = sendable if (spec, slot) in sendable else [*sendable, (spec, slot)]
            first.setdefault(key, [])
    for spec, slot in sendable:
        key = (spec.score_id, slot.slot)
        if _is_bound(result, *key):
            continue
        label = f"{key[0]}.{key[1]}"
        if rejected.get(label, "no fact chosen") != "no fact chosen":
            found, reason = first[key], rejected[label]
        else:
            seen = {fact.fact_id for fact in first[key]}
            found = slot_candidates(
                slot, facts, limit=_RETRY_CANDIDATES, skip=seen, weights=weights
            )
            reason = "no fact chosen"
        parts = component_candidates(slot, facts, weights)
        found = [*found, *(f for group in parts.values() for f in group if f not in found)]
        if found:
            retry_found[key] = found
            notes[key] = f"{reason}; candidates: {', '.join(fact.fact_id for fact in found)}"
            if parts:
                notes[key] += "\n" + _component_lines(parts)
            shown[key] = shown[key] + (
                0 if label in rejected and rejected[label] != "no fact chosen" else len(found)
            )
    if notes:
        retry_pairs = [(spec, slot) for spec, slot in pairs if (spec.score_id, slot.slot) in notes]
        wanted = {fact.fact_id for found in retry_found.values() for fact in found}
        again = await complete_as(
            provider,
            binding_messages(
                retry_pairs, [fact for fact in facts if fact.fact_id in wanted], notes
            ),
            BindingOutput,
            task=BIND_TASK,
        )
        result = _merge(result, validate_bindings(again, specs, index, basis))
    _apply_statement_rows(pairs, result, facts, index)
    for spec, slot in pairs:
        key = (spec.score_id, slot.slot)
        if slot.derive_from and not _is_bound(result, *key):
            derived = derive_deterministically(slot, facts, weights, basis)
            if derived is not None:
                result.bound[spec.score_id].append(derived)
                result.rejected = [
                    line for line in result.rejected if not line.startswith(f"{key[0]}.{key[1]}:")
                ]
    result.unbound = _unbound_reasons(pairs, result, shown, set(notes))
    return result


def _is_special(slot: InputSlot) -> bool:
    return bool(slot.mapping) or slot.judge is not None


def _hint(slot: InputSlot, reason: str) -> str:
    if slot.run_parameter:
        flag = "--" + slot.run_parameter.replace("_", "-")
        env = f"BUSYBEE_{slot.run_parameter.upper()}"
        return f"{reason}; the bank supplies it at run time ({flag} or {env})"
    return reason


async def _bind_special(
    provider: Provider,
    spec: ScoreSpec,
    slot: InputSlot,
    facts: list[VerifiedFact],
    sections: list[PolicySection],
) -> BoundInput | str:
    """Rating index from a stated grade (model only as a fallback), else a policy judgement."""
    if slot.mapping:
        bound = rating_binding(slot, facts)
        if bound is not None:
            return bound
    try:
        return await judge_slot(provider, spec, slot, facts, sections)
    except StructuredOutputError as error:
        return f"the judgement call failed: {error}"


def _apply_fallbacks(pairs: list[tuple[ScoreSpec, InputSlot]], result: BindingResult) -> None:
    """Let an unbound slot reuse the fact of its fallback slot, noting the substitution."""
    sources = {
        slot.slot: (slot, item)
        for spec, slot in pairs
        for item in result.bound.get(spec.score_id, [])
        if item.slot == slot.slot
    }
    for spec, slot in pairs:
        key = (spec.score_id, slot.slot)
        if not slot.fallback_slot or _is_bound(result, *key) or slot.fallback_slot not in sources:
            continue
        source_slot, item = sources[slot.fallback_slot]
        if (source_slot.unit, source_slot.scale) != (slot.unit, slot.scale):
            continue
        result.bound[spec.score_id].append(
            item.model_copy(update={"slot": slot.slot, "note": slot.fallback_note})
        )
        result.unbound.pop(key, None)


async def bind_inputs(
    provider: Provider,
    specs: list[ScoreSpec],
    facts: list[VerifiedFact],
    policy_sections: list[PolicySection] | None = None,
) -> BindingResult:
    """Bind every fact-backed slot: pick facts, map ratings, judge flags, apply fallbacks."""
    pairs = score_input_slots(specs)
    plain = [(spec, slot) for spec, slot in pairs if not _is_special(slot)]
    basis = reporting_basis(facts)
    result = await _bind_from_facts(provider, plain, specs, facts, basis)
    for spec, slot in pairs:
        if not _is_special(slot):
            continue
        outcome = await _bind_special(provider, spec, slot, facts, policy_sections or [])
        if isinstance(outcome, str):
            result.unbound[(spec.score_id, slot.slot)] = outcome
        else:
            result.bound[spec.score_id].append(outcome)
    _apply_fallbacks(pairs, result)
    for spec, slot in pairs:
        key = (spec.score_id, slot.slot)
        if key in result.unbound and slot.run_parameter:
            result.unbound[key] = _hint(slot, result.unbound[key])
    return result
