"""Deterministic sanity checks over bound score inputs, run after binding and before Lean.

`scores.yaml` may carry a top-level `invariants:` list of `{name, expression, message}`. An
expression is one comparison (`<`, `<=`, `>`, `>=`, `==`, `!=`) between arithmetic over slot
names, integer or decimal literals, `+`, `-`, `*`, unary minus and parentheses, parsed by a
tiny recursive-descent parser (never `eval`). Values are the slots' scaled integers, so slots
compared with each other should share a scale and a literal is in scaled units (zero is safe).

`check_invariants` returns a `Violation` for each rule whose slots are all bound and whose
comparison is false, with the fact ids behind those slots. `enforce_invariants` gives the
binder exactly one chance to fix a violation: it re-asks for just the involved slots, with the
rule's message in the retry notes (the same prompt shape as the binder's own retry), re-checks,
and keeps the new bindings only if they leave no more violations than before. Whatever is
still violated becomes a warning string per affected score (`ScoreResult.warnings`); the score
still computes and the Lean output is untouched, so the bank decides what to do.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, Field

from busybee.llm import Provider, complete_as
from busybee.policy.bind_inputs import (
    BIND_TASK,
    BindingOutput,
    binding_messages,
    score_input_slots,
    slot_candidates,
    validate_bindings,
)
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import BoundInput, Invariant, ScoreSpec

_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|==|!=|[-+*()<>]))")
_COMPARATORS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}
_RETRY_CANDIDATES = 15

Node = tuple


class InvariantError(ValueError):
    """The expression is not a valid invariant."""


class Violation(BaseModel):
    """One failed invariant: the rule, the slots it reads, and the facts bound to them."""

    name: str
    expression: str
    message: str
    slots: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


def _tokens(text: str) -> list[str]:
    found, position = [], 0
    while position < len(text.rstrip()):
        match = _TOKEN.match(text, position)
        if match is None:
            raise InvariantError(f"unexpected character at {text[position:].strip()[:10]!r}")
        found.append(match.group(0).strip())
        position = match.end()
    return found


@dataclass
class _Parser:
    tokens: list[str]
    position: int = 0

    def peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise InvariantError("unexpected end of expression")
        self.position += 1
        return token

    def sum(self) -> Node:
        node = self.product()
        while self.peek() in ("+", "-"):
            node = (self.take(), node, self.product())
        return node

    def product(self) -> Node:
        node = self.factor()
        while self.peek() == "*":
            node = (self.take(), node, self.factor())
        return node

    def factor(self) -> Node:
        token = self.take()
        if token == "-":
            return ("neg", self.factor())
        if token == "(":
            node = self.sum()
            if self.take() != ")":
                raise InvariantError("missing closing parenthesis")
            return node
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            return ("num", Decimal(token))
        if re.fullmatch(r"[A-Za-z_]\w*", token):
            return ("slot", token)
        raise InvariantError(f"unexpected token {token!r}")


def parse_expression(text: str) -> tuple[str, Node, Node]:
    """Parse `left <op> right` into (operator, left tree, right tree)."""
    parser = _Parser(_tokens(text))
    left = parser.sum()
    operator = parser.take() if parser.peek() in _COMPARATORS else None
    if operator is None:
        raise InvariantError("expected a comparison operator")
    right = parser.sum()
    if parser.peek() is not None:
        raise InvariantError(f"unexpected trailing token {parser.peek()!r}")
    return operator, left, right


def expression_slots(node: Node | tuple[str, Node, Node]) -> list[str]:
    """Slot names an expression (or parsed comparison) reads, in order, without repeats."""
    if node[0] == "slot":
        return [node[1]]
    if node[0] == "num":
        return []
    found = []
    for child in node[1:]:
        if isinstance(child, tuple):
            found.extend(expression_slots(child))
    return list(dict.fromkeys(found))


def node_value(node: Node, values: dict[str, int]) -> Decimal:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "slot":
        return Decimal(values[node[1]])
    if kind == "neg":
        return -node_value(node[1], values)
    left, right = node_value(node[1], values), node_value(node[2], values)
    return {"+": left + right, "-": left - right, "*": left * right}[kind]


def evaluate_expression(text: str, values: dict[str, int]) -> bool:
    """Evaluate an invariant over slot -> scaled integer values; every slot must be present."""
    operator, left, right = parse_expression(text)
    return _COMPARATORS[operator](node_value(left, values), node_value(right, values))


def _slot_inputs(bound: dict[str, list[BoundInput]]) -> dict[str, BoundInput]:
    found: dict[str, BoundInput] = {}
    for items in bound.values():
        for item in items:
            found.setdefault(item.slot, item)
    return found


def check_invariants(
    invariants: list[Invariant], bound: dict[str, list[BoundInput]]
) -> list[Violation]:
    """Violations among invariants whose slots are all bound; unbound ones are skipped."""
    inputs = _slot_inputs(bound)
    violations = []
    for rule in invariants:
        operator, left, right = parse_expression(rule.expression)
        slots = expression_slots((operator, left, right))
        if any(slot not in inputs for slot in slots):
            continue
        values = {slot: inputs[slot].value_scaled for slot in slots}
        if _COMPARATORS[operator](node_value(left, values), node_value(right, values)):
            continue
        ids: list[str] = []
        for slot in slots:
            ids.extend([inputs[slot].fact_id, *inputs[slot].derived_from])
        violations.append(
            Violation(
                name=rule.name,
                expression=rule.expression,
                message=rule.message or f"Invariant {rule.name} violated",
                slots=slots,
                fact_ids=[fact_id for fact_id in dict.fromkeys(ids) if fact_id],
            )
        )
    return violations


def _retry_notes(
    pairs: list[tuple[ScoreSpec, object]],
    violations: list[Violation],
    bound: dict[str, list[BoundInput]],
) -> dict[tuple[str, str], str]:
    notes = {}
    for spec, slot in pairs:
        slot_name = slot.slot  # type: ignore[attr-defined]
        current = next((b for b in bound.get(spec.score_id, []) if b.slot == slot_name), None)
        rules = "; ".join(
            f"{v.message} (rule {v.expression}, facts {', '.join(v.fact_ids)})"
            for v in violations
            if slot_name in v.slots
        )
        now = f"currently {current.value} from {current.fact_id}" if current else "unbound"
        notes[(spec.score_id, slot_name)] = (
            f"sanity check failed: {rules}. This slot is {now}. Rebind it if a different "
            "period, scope or definition is the cause; otherwise keep the same fact."
        )
    return notes


async def _rebind(
    provider: Provider,
    specs: list[ScoreSpec],
    facts: list[VerifiedFact],
    violations: list[Violation],
    bound: dict[str, list[BoundInput]],
) -> dict[str, list[BoundInput]]:
    """One binder call for the violated slots; returns bound with any valid new bindings."""
    involved = {slot for v in violations for slot in v.slots}
    pairs = [
        (spec, slot)
        for spec, slot in score_input_slots(specs)
        if slot.slot in involved and not (slot.mapping or slot.judge or slot.run_parameter)
    ]
    if not pairs:
        return bound
    notes = _retry_notes(pairs, violations, bound)
    wanted = {fact_id for v in violations for fact_id in v.fact_ids}
    for _, slot in pairs:
        wanted.update(f.fact_id for f in slot_candidates(slot, facts, limit=_RETRY_CANDIDATES))
    output = await complete_as(
        provider,
        binding_messages(pairs, [f for f in facts if f.fact_id in wanted], notes),
        BindingOutput,
        task=BIND_TASK,
    )
    again = validate_bindings(output, specs, {f.fact_id: f for f in facts})
    updated = {score_id: list(items) for score_id, items in bound.items()}
    for score_id, items in again.bound.items():
        fresh = {item.slot: item for item in items}
        updated[score_id] = [fresh.pop(i.slot, i) for i in updated.get(score_id, [])]
    return updated


def warnings_by_score(
    violations: list[Violation], bound: dict[str, list[BoundInput]]
) -> dict[str, list[str]]:
    """Warning strings per score id, for every score that takes a slot a violation reads."""
    result: dict[str, list[str]] = {}
    for score_id, items in bound.items():
        have = {item.slot for item in items}
        for violation in violations:
            if have & set(violation.slots):
                ids = ", ".join(violation.fact_ids)
                text = f"{violation.message} [{violation.expression}; facts {ids}]"
                result.setdefault(score_id, []).append(text)
    return result


async def enforce_invariants(
    provider: Provider,
    specs: list[ScoreSpec],
    invariants: list[Invariant],
    facts: list[VerifiedFact],
    bound: dict[str, list[BoundInput]],
) -> tuple[dict[str, list[BoundInput]], dict[str, list[str]]]:
    """Check, give the binder one retry on violations, re-check; return bindings and warnings."""
    violations = check_invariants(invariants, bound)
    if not violations:
        return bound, {}
    retried = await _rebind(provider, specs, facts, violations, bound)
    after = check_invariants(invariants, retried)
    if len(after) <= len(violations):
        bound, violations = retried, after
    return bound, warnings_by_score(violations, bound)
