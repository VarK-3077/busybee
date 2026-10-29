"""Build the per-run `Scores.lean` from a bank policy module, bound facts, and score specs.

The file imports the synced policy module and has three sections. `-- SECTION: Facts` has one
`def` per bound slot with its provenance comment (`-- F012 D1:p214:c2`). `-- SECTION: Scores`
defines each score's value and grade by calling the policy functions and prints
`<score_id>=<value>` and `<score_id>_grade=<grade>` with `#eval`; those lines are the only
place a score is ever computed. `-- SECTION: Checks` holds one theorem per score pinning the
value and grade Lean printed, proved by `decide`; it is empty on the first (evaluation) pass.
A slot named after another score uses that score's Lean value instead of a fact.

`-- SECTION: Policy rules` has, for every rule whose inputs are all bound, a `Bool` def per
condition, a status def (`pass` / `caution` / `fail`) and an `#eval` printing
`rule_<id>=<status>`. On the pinning pass each rule also gets a theorem that `decide` proves:
the status Lean printed, and the condition itself (or its negation when it is violated).
`rule_bindings` resolves each rule's slots to the defs above; rules with an unbound slot are
left out and reported `not_evaluable` by the caller.

A score with a `ScoreAdjustment` (`bands.py`: a band reads a proxy or incomplete input) gets
those band calls subtracted from the policy's value, so the band awards 0 points, and its grade
is read off the policy's grade ladder applied to the adjusted value.
"""

import json
import re

from busybee.lean import templates
from busybee.policy.bands import ScoreAdjustment
from busybee.policy.rules import (
    ResolvedRule,
    lean_condition,
    lean_fail_status,
    lean_rule_name,
    rule_slots,
)
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, PolicyRule, RuleOutcome, ScoreSpec

_UNSAFE = re.compile(r"\W")


def lean_name(text: str) -> str:
    """Make text safe as a Lean identifier part."""
    return _UNSAFE.sub("_", text)


def fact_def_name(score_id: str, slot: str) -> str:
    """Name of the Lean def that holds one bound slot value."""
    return f"{lean_name(score_id)}_{lean_name(slot)}"


def is_score_slot(spec: ScoreSpec, slot: InputSlot, score_ids: set[str]) -> bool:
    """True when the slot takes another score's computed value rather than a fact."""
    return slot.slot in score_ids and slot.slot != spec.score_id


def missing_slots(
    spec: ScoreSpec, bound: list[BoundInput], score_ids: set[str], ready: set[str]
) -> list[str]:
    """Slots that have neither a bound fact nor an already computable score."""
    have = {item.slot for item in bound}
    return [
        slot.slot
        for slot in spec.inputs
        if slot.slot not in have
        and not (is_score_slot(spec, slot, score_ids) and slot.slot in ready)
    ]


def computable_scores(
    specs: list[ScoreSpec], bound: dict[str, list[BoundInput]]
) -> list[ScoreSpec]:
    """Scores whose slots are all bound, ordered so dependencies come first."""
    score_ids = {spec.score_id for spec in specs}
    ready: list[ScoreSpec] = []
    ready_ids: set[str] = set()
    progress = True
    while progress:
        progress = False
        for spec in specs:
            if spec.score_id in ready_ids:
                continue
            if not missing_slots(spec, bound.get(spec.score_id, []), score_ids, ready_ids):
                ready.append(spec)
                ready_ids.add(spec.score_id)
                progress = True
    return ready


def _provenance(facts: dict[str, VerifiedFact], item: BoundInput) -> str:
    parts: list[str] = []
    for fact_id in item.derived_from or [item.fact_id]:
        fact = facts.get(fact_id)
        chunks = [citation.chunk_id for citation in fact.citations] if fact else []
        parts.extend([fact_id, *chunks])
    text = " ".join(parts)
    note = " ".join(item.note.split())
    return f"{text} | note: {note}" if note else text


def rule_bindings(
    rules: list[PolicyRule],
    specs: list[ScoreSpec],
    bound: dict[str, list[BoundInput]],
    reasons: dict[str, str] | None = None,
) -> dict[str, ResolvedRule]:
    """Resolve every rule slot to a Lean def name; unresolved slots are listed with a reason.

    A score id resolves to that score's `_value` def when the score is computable; any other
    name resolves to the bound fact of the first score that takes the slot.
    """
    ready_ids = {spec.score_id for spec in computable_scores(specs, bound)}
    score_ids = {spec.score_id for spec in specs}
    why = reasons or {}
    resolved: dict[str, ResolvedRule] = {}
    for rule in rules:
        info = ResolvedRule()
        for name in rule_slots(rule):
            if name in score_ids:
                if name in ready_ids:
                    info.names[name] = f"{lean_name(name)}_value"
                    info.score_ids.append(name)
                else:
                    info.missing[name] = f"score {name} is not computable"
                continue
            owner = next(
                (
                    (spec.score_id, item)
                    for spec in specs
                    for item in bound.get(spec.score_id, [])
                    if item.slot == name
                ),
                None,
            )
            if owner is None:
                info.missing[name] = why.get(name, "not bound")
                continue
            info.names[name] = fact_def_name(owner[0], name)
            info.inputs.append(owner[1])
        resolved[rule.rule_id] = info
    return resolved


def _facts_section(
    specs: list[ScoreSpec], bound: dict[str, list[BoundInput]], facts: dict[str, VerifiedFact]
) -> str:
    parts = [templates.section("Facts")]
    for spec in specs:
        slots = {slot.slot: slot for slot in spec.inputs}
        for item in bound.get(spec.score_id, []):
            slot = slots[item.slot]
            doc = f"{spec.score_id} input {item.slot}: {slot.description} ({slot.unit})."
            parts.append(
                templates.fact_def(
                    fact_def_name(spec.score_id, item.slot),
                    item.value_scaled,
                    _provenance(facts, item),
                    doc,
                )
            )
    return "\n\n".join(parts)


def _call(namespace: str, function: str, spec: ScoreSpec, score_ids: set[str]) -> str:
    arguments = [
        f"{lean_name(slot.slot)}_value"
        if is_score_slot(spec, slot, score_ids)
        else fact_def_name(spec.score_id, slot.slot)
        for slot in spec.inputs
    ]
    return " ".join([f"{namespace}.{function}", *arguments])


def _argument(spec: ScoreSpec, slot_name: str, score_ids: set[str]) -> str:
    slot = next((s for s in spec.inputs if s.slot == slot_name), None)
    if slot is not None and is_score_slot(spec, slot, score_ids):
        return f"{lean_name(slot.slot)}_value"
    return fact_def_name(spec.score_id, slot_name)


def _adjusted(
    namespace: str,
    spec: ScoreSpec,
    score_ids: set[str],
    adjustment: ScoreAdjustment,
    call: str,
    grade_call: str,
) -> tuple[str, str]:
    """The score call minus every excluded band, and a grade from the adjusted value."""
    for band in adjustment.bands:
        args = [
            _argument(spec, adjustment.slot_of.get(name, name), score_ids)
            for name in band.arguments
        ]
        call = f"{call} - ({' '.join([f'{namespace}.{band.function}', *args])})"
    if not adjustment.steps:
        return call, grade_call
    value = f"{lean_name(spec.score_id)}_value"
    ladder = " else ".join(
        f"if {threshold} ≤ {value} then {json.dumps(label, ensure_ascii=False)}"
        for threshold, label in adjustment.steps
    )
    return call, f"{ladder} else {json.dumps(adjustment.floor, ensure_ascii=False)}"


def _scores_section(
    namespace: str,
    ready: list[ScoreSpec],
    score_ids: set[str],
    adjustments: dict[str, ScoreAdjustment] | None = None,
) -> str:
    parts = [templates.section("Scores")]
    for spec in ready:
        sid = lean_name(spec.score_id)
        call = _call(namespace, spec.lean_function, spec, score_ids)
        grade_call = _call(namespace, f"{spec.lean_function}_grade", spec, score_ids)
        adjustment = (adjustments or {}).get(spec.score_id)
        if adjustment is not None:
            call, grade_call = _adjusted(namespace, spec, score_ids, adjustment, call, grade_call)
        parts.append(
            f"/-- {spec.name}, computed by the bank policy. -/\ndef {sid}_value : Int := {call}"
        )
        parts.append(
            f"/-- Grade label of {spec.name}. -/\ndef {sid}_grade_label : String := {grade_call}"
        )
        parts.append(templates.eval_line(f'IO.println s!"{sid}={{{sid}_value}}"'))
        parts.append(templates.eval_line(f'IO.println s!"{sid}_grade={{{sid}_grade_label}}"'))
    return "\n\n".join(parts)


def _checks_section(ready: list[ScoreSpec], pinned: dict[str, tuple[str, str]] | None) -> str:
    parts = [templates.section("Checks")]
    for spec in ready:
        if pinned is None or spec.score_id not in pinned:
            continue
        sid = lean_name(spec.score_id)
        value, grade = pinned[spec.score_id]
        parts.append(
            templates.theorem(
                f"{sid}_value_is",
                f"{sid}_value = {int(value)}",
                doc=f"Lean proves the {spec.name} equals {int(value)}.",
            )
        )
        parts.append(
            templates.theorem(
                f"{sid}_grade_is",
                f"{sid}_grade_label = {json.dumps(grade, ensure_ascii=False)}",
                doc=f"Lean proves the {spec.name} grade is {grade}.",
            )
        )
    return "\n\n".join(parts)


def _rule_pins(rule: PolicyRule, name: str, condition: str, zone: str, status: str) -> list[str]:
    stem = lean_rule_name(rule.rule_id)
    parts = [
        templates.theorem(
            f"{stem}_status_is",
            f'{stem}_status = "{status}"',
            doc=f"Lean proves rule {rule.rule_id} ({rule.name}) has status {status}.",
        )
    ]
    holds = status == "pass" or (status == "caution" and rule.outcome is not RuleOutcome.caution)
    if holds:
        parts.append(
            templates.theorem(
                f"{stem}_met",
                condition,
                doc=f"Lean proves the condition of rule {rule.rule_id} holds.",
            )
        )
    else:
        parts.append(
            templates.theorem(
                f"{stem}_violated",
                f"¬ ({condition})",
                doc=f"Lean proves the condition of rule {rule.rule_id} is violated.",
            )
        )
    if status == "caution" and holds:
        parts.append(
            templates.theorem(
                f"{stem}_in_caution_zone",
                zone,
                doc=f"Lean proves the borrower is inside the caution zone of rule {rule.rule_id}.",
            )
        )
    return parts


def _rules_section(
    rules: list[PolicyRule],
    resolved: dict[str, ResolvedRule],
    pinned: dict[str, str] | None,
) -> str:
    parts = [templates.section("Policy rules")]
    for rule in rules:
        info = resolved.get(rule.rule_id)
        if info is None or info.missing:
            continue
        stem = lean_rule_name(rule.rule_id)
        condition = lean_condition(rule.expression, info.names)
        zone = (
            lean_condition(rule.caution_expression, info.names) if rule.caution_expression else ""
        )
        parts.append(
            f"/-- Rule {rule.rule_id} ({rule.name}), policy section {rule.policy_section}: "
            f"{' '.join(rule.message.split())} -/\ndef {stem}_holds : Bool := decide ({condition})"
        )
        if zone:
            parts.append(
                f"/-- Caution zone of rule {rule.rule_id}. -/\n"
                f"def {stem}_in_zone : Bool := decide ({zone})"
            )
            inner = f'(if {stem}_in_zone then "caution" else "pass")'
        else:
            inner = '"pass"'
        parts.append(
            f"/-- Status of rule {rule.rule_id}: pass, caution or fail. -/\n"
            f"def {stem}_status : String :=\n"
            f'  if {stem}_holds then {inner} else "{lean_fail_status(rule)}"'
        )
        parts.append(templates.eval_line(f'IO.println s!"{stem}={{{stem}_status}}"'))
        if pinned is not None and rule.rule_id in pinned:
            parts.extend(_rule_pins(rule, stem, condition, zone, pinned[rule.rule_id]))
    return "\n\n".join(parts)


def build_scores_lean(
    policy_module: str,
    specs: list[ScoreSpec],
    bound: dict[str, list[BoundInput]],
    facts: dict[str, VerifiedFact],
    pinned: dict[str, tuple[str, str]] | None = None,
    rules: list[PolicyRule] | None = None,
    resolved: dict[str, ResolvedRule] | None = None,
    rule_pins: dict[str, str] | None = None,
    adjustments: dict[str, ScoreAdjustment] | None = None,
) -> str:
    """Render Scores.lean for the computable scores and rules; pinned adds the proof section."""
    score_ids = {spec.score_id for spec in specs}
    ready = computable_scores(specs, bound)
    header = templates.file_header(
        ["BusyBee.Common", policy_module],
        "# Scores for this run\n\nBound facts, the bank-defined score functions applied to them,\n"
        "`#eval` lines whose stdout carries the values, and `decide` proofs of those values.",
    )
    return templates.join(
        [
            header,
            _facts_section(specs, bound, facts),
            _scores_section(policy_module, ready, score_ids, adjustments),
            _checks_section(ready, pinned),
            _rules_section(rules or [], resolved or {}, rule_pins) if rules else "",
        ]
    )
