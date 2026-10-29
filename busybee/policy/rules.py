"""Policy rules: parse a rule's expression, translate it to Lean, and build `RuleResult`s.

A `PolicyRule` (`scores.yaml` `rules:`) carries an `expression` that must hold. It reuses the
`invariants.py` parser for each comparison and adds `and` / `or` between comparisons (`and`
binds tighter, no boolean parentheses). Only integer literals are allowed, so every threshold is
cross-multiplied (`100 * cfads >= 125 * debt_service`) and Lean stays division-free.

A rule that holds but whose inputs carry a caution (a missing component, a proxy, consolidated
and standalone figures mixed) is shown as `caution` with the reason in `caution_reason` and in the
inputs' notes; `fail` stays `fail`. A rule with a `measure` also gets its computed ratio and the
minimum standard (`computed_value`, `threshold`) so a report can name each failed criterion.

`lean_condition` renders an expression as a Lean `Prop` over a slot -> Lean name map, which
`generate.py` wraps in `decide`. Lean alone decides the status: `fail` when the expression is
false (`caution` instead for a rule whose outcome is `caution`), `caution` when it holds but the
optional `caution_expression` is true, else `pass`. `build_rule_results` joins the printed
statuses with the inputs each rule read; a rule with an unbound input is `not_evaluable`.
"""

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from busybee.policy.invariants import (
    InvariantError,
    Node,
    expression_slots,
    node_value,
    parse_expression,
)
from busybee.policy.policy_sections import PolicySection
from busybee.schema.facts import VerifiedFact
from busybee.schema.lean import LeanArtifact
from busybee.schema.policy import (
    BoundInput,
    PolicyRule,
    RuleOutcome,
    RuleResult,
    RuleStatus,
    ScoreSpec,
)

_OR = re.compile(r"\s+or\s+")
_AND = re.compile(r"\s+and\s+")
_LEAN_COMPARATORS = {"<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=", "!=": "≠"}
_PRECEDENCE = {"+": 1, "-": 1, "*": 2}
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")
RULE_PREFIX = "rule_"
STANDALONE_NOTE = "standalone figures: the documents hold no consolidated statements"

Disjunction = list[list[tuple[str, Node, Node]]]


class RuleError(ValueError):
    """The rule's expression or definition is not usable."""


@dataclass
class ResolvedRule:
    """How one rule's slots resolve in a run: Lean names, bound inputs and what is missing."""

    names: dict[str, str] = field(default_factory=dict)
    inputs: list[BoundInput] = field(default_factory=list)
    score_ids: list[str] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)


def parse_condition(text: str) -> Disjunction:
    """Parse `a op b and c op d or ...` into disjuncts of conjoined comparisons."""
    try:
        return [
            [parse_expression(part) for part in _AND.split(clause.strip())]
            for clause in _OR.split(text.strip())
        ]
    except InvariantError as error:
        raise RuleError(f"{text!r}: {error}") from error


def condition_slots(text: str) -> list[str]:
    """Slot names and score ids a condition reads, without repeats."""
    names = [
        name
        for clause in parse_condition(text)
        for comparison in clause
        for name in expression_slots(comparison)
    ]
    return list(dict.fromkeys(names))


def rule_slots(rule: PolicyRule) -> list[str]:
    """Every slot name or score id the rule reads, in order of appearance."""
    texts = [rule.expression, *([rule.caution_expression] if rule.caution_expression else [])]
    return list(dict.fromkeys(name for text in texts for name in condition_slots(text)))


def _literals(node: Node) -> list[Decimal]:
    if node[0] == "num":
        return [node[1]]
    if node[0] == "slot":
        return []
    return [value for child in node[1:] if isinstance(child, tuple) for value in _literals(child)]


def validate_rule(rule: PolicyRule, known_names: set[str]) -> None:
    """Raise RuleError when the rule cannot be evaluated or names an unknown slot."""
    if rule.caution_expression and rule.outcome is RuleOutcome.caution:
        raise RuleError(f"{rule.rule_id}: a caution rule cannot have a caution_expression")
    for text in (rule.expression, rule.caution_expression):
        if not text:
            continue
        for clause in parse_condition(text):
            for _, left, right in clause:
                if any(
                    value != value.to_integral_value()
                    for value in _literals(left) + _literals(right)
                ):
                    raise RuleError(f"{rule.rule_id}: use integer literals only ({text!r})")
        unknown = sorted(set(condition_slots(text)) - known_names)
        if unknown:
            raise RuleError(f"{rule.rule_id}: unknown slot or score {', '.join(unknown)}")


def _render(node: Node, names: dict[str, str], parent: int = 0) -> str:
    kind = node[0]
    if kind == "num":
        return str(int(node[1]))
    if kind == "slot":
        return names[node[1]]
    if kind == "neg":
        return f"(-{_render(node[1], names, 3)})"
    precedence = _PRECEDENCE[kind]
    text = f"{_render(node[1], names, precedence)} {kind} {_render(node[2], names, precedence + 1)}"
    return f"({text})" if precedence < parent else text


def lean_condition(text: str, names: dict[str, str]) -> str:
    """Render a condition as a Lean proposition over the given slot -> Lean name map."""
    clauses = []
    for clause in parse_condition(text):
        comparisons = [
            f"{_render(left, names)} {_LEAN_COMPARATORS[operator]} {_render(right, names)}"
            for operator, left, right in clause
        ]
        clauses.append(" ∧ ".join(comparisons))
    if len(clauses) == 1:
        return clauses[0]
    return " ∨ ".join(f"({clause})" for clause in clauses)


def lean_rule_name(rule_id: str) -> str:
    """The Lean identifier stem of a rule: `rule_<id>`."""
    return RULE_PREFIX + re.sub(r"\W", "_", rule_id)


def lean_fail_status(rule: PolicyRule) -> str:
    """The status Lean reports when the expression is false."""
    return (
        RuleStatus.caution.value if rule.outcome is RuleOutcome.caution else RuleStatus.fail.value
    )


def parse_rule_statuses(stdout: str, rules: list[PolicyRule]) -> dict[str, str]:
    """Statuses printed by the generated `#eval` lines (`rule_<id>=pass|fail|caution`)."""
    stems = {lean_rule_name(rule.rule_id): rule.rule_id for rule in rules}
    found = {}
    for line in stdout.splitlines():
        key, _, text = line.strip().partition("=")
        if key in stems and text.strip() in {"pass", "fail", "caution"}:
            found[stems[key]] = text.strip()
    return found


def policy_section_id(sections: list[PolicySection], reference: str) -> str:
    """Section id (P5) of the policy.md section numbered `reference` ("4" or "10.1")."""
    wanted = reference.strip().lstrip("§").strip()
    for section in sections:
        match = _SECTION_NUMBER.match(section.heading)
        if wanted and match and match.group(1) == wanted:
            return section.section_id
    return ""


def add_score_inputs(
    resolved: dict[str, ResolvedRule], specs: list[ScoreSpec], values: dict[str, str]
) -> None:
    """Append the Lean-computed value of every score a rule reads to that rule's inputs."""
    by_id = {spec.score_id: spec for spec in specs}
    for info in resolved.values():
        for score_id in info.score_ids:
            raw = values.get(score_id)
            if raw is None or not raw.lstrip("-").isdigit():
                continue
            spec = by_id[score_id]
            info.inputs.append(
                BoundInput(
                    slot=score_id,
                    fact_id="",
                    value=Decimal(raw) / spec.value_scale,
                    unit=spec.unit,
                    value_scaled=int(raw),
                    note="score computed by Lean from the bound facts",
                )
            )


def scope_conflict(inputs: list[BoundInput], facts: dict[str, VerifiedFact]) -> str:
    """Say so when the inputs rest on both consolidated and standalone facts, else empty."""
    by_scope: dict[str, list[str]] = {}
    for item in inputs:
        for fact_id in dict.fromkeys([item.fact_id, *item.derived_from]):
            fact = facts.get(fact_id)
            if fact is not None and fact.scope is not None:
                by_scope.setdefault(fact.scope.value, []).append(fact_id)
    if len(by_scope) < 2:
        return ""
    parts = " and ".join(f"{scope} ({', '.join(ids)})" for scope, ids in sorted(by_scope.items()))
    return f"inputs mix bases: {parts}"


def rule_measure(rule: PolicyRule, inputs: list[BoundInput]) -> tuple[str, str]:
    """The rule's computed ratio and minimum standard as text ("4.71x", "at most 4.5x")."""
    if not (rule.measure and rule.measure_numerator and rule.measure_denominator):
        return "", ""
    values = {item.slot: item.value_scaled for item in inputs}
    try:
        top, bottom = (
            node_value(parse_expression(f"{text} == 0")[1], values)
            for text in (rule.measure_numerator, rule.measure_denominator)
        )
    except (KeyError, InvariantError):
        return "", rule.limit_text
    if bottom == 0:
        return "not defined", rule.limit_text
    ratio = top / bottom
    if rule.measure_unit == "%":
        shown = f"{(ratio * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"
    else:
        shown = f"{ratio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}{rule.measure_unit}"
    return shown, rule.limit_text


def _annotated(inputs: list[BoundInput], extra: str) -> list[BoundInput]:
    return [
        item.model_copy(update={"note": "; ".join(part for part in (item.note, extra) if part)})
        if item.fact_id
        else item
        for item in inputs
    ]


def build_rule_results(
    rules: list[PolicyRule],
    resolved: dict[str, ResolvedRule],
    statuses: dict[str, str],
    artifact: LeanArtifact | None,
    sections: list[PolicySection],
    facts: dict[str, VerifiedFact] | None = None,
    basis: str = "",
) -> list[RuleResult]:
    """One RuleResult per rule: Lean's status when evaluable, else `not_evaluable`."""
    results = []
    for rule in rules:
        info = resolved.get(rule.rule_id, ResolvedRule())
        printed = statuses.get(rule.rule_id)
        evaluable = not info.missing and printed is not None
        status = RuleStatus(printed) if evaluable and printed else RuleStatus.not_evaluable
        inputs = info.inputs
        reasons = [item.caution for item in inputs if item.caution]
        conflict = scope_conflict(inputs, facts or {})
        if conflict:
            reasons.append(conflict)
            inputs = _annotated(inputs, conflict)
        if basis == "standalone":
            inputs = _annotated(inputs, STANDALONE_NOTE)
        if status is RuleStatus.passed and reasons:
            status = RuleStatus.caution
        shown, limit = rule_measure(rule, inputs) if evaluable else ("", "")
        results.append(
            RuleResult(
                rule_id=rule.rule_id,
                name=rule.name,
                status=status,
                outcome=rule.outcome,
                message=rule.message,
                expression=rule.expression,
                inputs=inputs,
                score_ids=info.score_ids,
                unbound=info.missing
                or ({} if evaluable else {"lean": "the Lean file did not produce a result"}),
                policy_section=rule.policy_section,
                policy_section_id=policy_section_id(sections, rule.policy_section),
                lean=artifact if not info.missing else None,
                basis=basis,
                caution_reason="; ".join(reasons),
                measure=rule.measure if shown else "",
                computed_value=shown,
                threshold=limit,
            )
        )
    return results
