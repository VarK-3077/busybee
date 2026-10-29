"""The policy-implied decision floor: what the Lean-evaluated rules force, enforced in code.

Every `RuleResult` implies a minimum decision. A failing `decline` rule forces decline, a failing
`refer` rule forces at least refer, a `caution` status (a rule in its caution zone, or a failing
`caution` rule) and a failing `pass_required` rule force at least approve with conditions;
passing and `not_evaluable` rules force nothing. A failing minimum-standard rule (see
`minimum_standards.py`) implies `reduce_or_decline` whatever its outcome. Decisions are ordered
approve < approve with conditions < refer < reduce or decline < decline and the floor is the
strictest one any rule implies.

`enforce_policy_floor` replaces a model decision more lenient than the floor: the headline comes
from a template ("Refer: <rule message>"), a proposed limit is dropped for refer and decline,
the confidence note records the override, and a `DecisionOverride` is returned for the audit.
For `reduce_or_decline` the headline is always rebuilt from the failed minimum standards, with the
model's proposed limit only when it fits `max_exposure_crore`; when the maximum exposure score is
not evaluable or zero (`exposure_limit_note`), no amount is stated and the headline says why:
"The proposed limit could not be computed: <reason>." or "The policy permits no exposure at
internal risk grade 7, so the proposed INR 150 crore cannot be sanctioned." (grade and amount
from the scores). A zero exposure does not change the decision: the policy declines only at the
worst grade, which the decline rule already enforces.
`headline_matches_decision` checks the leading verb of a headline against a decision (approve,
approved, sanction; refer, referral, committee; decline, reject), and `rebuild_headline` writes
"<Decision label>: <message of the rule that determined the decision, else the model's text>"
with the proposed amount only for approve decisions; `run_compose` uses both after the floor so the
headline never contradicts the final decision.
`add_missing_rule_reasons` appends, for each failing or caution rule that no reason cites, a
`policy_rule` reason built from the rule's message, its inputs' fact ids and its policy section.
`unevaluated_note` names rules that could not be evaluated so the confidence note says so.
"""

import re
from decimal import Decimal

from busybee.schema.policy import RuleOutcome, RuleResult, RuleStatus, ScoreResult, ScoreStatus
from busybee.schema.report import (
    Decision,
    DecisionOverride,
    KeyReason,
    PolicyCitation,
    Recommendation,
)

from .minimum_standards import REDUCE_LABEL, is_minimum_standard, minimum_headline

DECISION_RANK = {
    Decision.approve: 0,
    Decision.approve_with_conditions: 1,
    Decision.refer: 2,
    Decision.reduce_or_decline: 3,
    Decision.decline: 4,
}
_HEADLINE_LABELS = {
    Decision.approve: "Approve",
    Decision.approve_with_conditions: "Approve with conditions",
    Decision.refer: "Refer",
    Decision.decline: "Decline",
    Decision.reduce_or_decline: REDUCE_LABEL,
}
_FAIL_DECISIONS = {
    RuleOutcome.decline: Decision.decline,
    RuleOutcome.refer: Decision.refer,
    RuleOutcome.caution: Decision.approve_with_conditions,
    RuleOutcome.pass_required: Decision.approve_with_conditions,
}


def rule_decision(result: RuleResult) -> Decision:
    """The minimum decision one rule result implies."""
    if result.status is RuleStatus.fail:
        if is_minimum_standard(result) and result.outcome is not RuleOutcome.decline:
            return Decision.reduce_or_decline
        return _FAIL_DECISIONS[result.outcome]
    if result.status is RuleStatus.caution:
        if result.outcome is RuleOutcome.caution:
            return Decision.approve_with_conditions
        return Decision.refer
    return Decision.approve


def policy_floor(results: list[RuleResult]) -> tuple[Decision, list[RuleResult]]:
    """The strictest implied decision and the rule results that imply exactly that."""
    floor = max(
        (rule_decision(result) for result in results),
        key=DECISION_RANK.__getitem__,
        default=Decision.approve,
    )
    binding = [
        result
        for result in results
        if rule_decision(result) is floor and floor is not Decision.approve
    ]
    return floor, binding


def floor_headline(decision: Decision, binding: list[RuleResult]) -> str:
    """The template headline: the decision label, then the first binding rule's message."""
    if decision is Decision.reduce_or_decline:
        return minimum_headline(binding)
    label = _HEADLINE_LABELS.get(decision, decision.value)
    first = binding[0].message or binding[0].name
    more = f" (and {len(binding) - 1} more policy rule(s))" if len(binding) > 1 else ""
    return f"{label}: {first}{more}"


_VERB_DECISIONS = {
    "approve": (Decision.approve, Decision.approve_with_conditions),
    "approved": (Decision.approve, Decision.approve_with_conditions),
    "sanction": (Decision.approve, Decision.approve_with_conditions),
    "refer": (Decision.refer,),
    "referral": (Decision.refer,),
    "committee": (Decision.refer,),
    "decline": (Decision.decline,),
    "declined": (Decision.decline,),
    "reduce": (Decision.reduce_or_decline,),
    "reject": (Decision.decline,),
    "rejected": (Decision.decline,),
}


def headline_matches_decision(headline: str, decision: Decision) -> bool:
    """Whether the headline's leading verb fits the decision; unknown verbs never do."""
    words = headline.strip().split()
    verb = words[0].strip(".,:;-").lower() if words else ""
    return decision in _VERB_DECISIONS.get(verb, ())


def headline_rule(decision: Decision, rule_results: list[RuleResult]) -> RuleResult | None:
    """The first rule that floors at the decision, else the first flagged rule, else None."""
    flagged = [r for r in rule_results if r.status in (RuleStatus.fail, RuleStatus.caution)]
    determining = [r for r in flagged if rule_decision(r) is decision]
    return next(iter(determining or flagged), None)


def rebuild_headline(
    decision: Decision,
    rule_results: list[RuleResult],
    model_headline: str,
    proposed_limit: str | None = None,
    max_exposure: Decimal | None = None,
    limit_note: str = "",
) -> str:
    """The "<Decision label>: <determining rule message>" headline; amount on approve."""
    if decision is Decision.reduce_or_decline:
        return minimum_headline(
            rule_results, [model_headline, proposed_limit or ""], max_exposure, limit_note
        )
    label = _HEADLINE_LABELS[decision]
    rule = headline_rule(decision, rule_results)
    reason = (rule.message or rule.name) if rule else model_headline.strip()
    amount = (
        f" ({proposed_limit})"
        if proposed_limit and decision in (Decision.approve, Decision.approve_with_conditions)
        else ""
    )
    return f"{label}{amount}: {reason}" if reason else f"{label}{amount}"


def max_exposure_crore(scores: list[ScoreResult]) -> Decimal | None:
    """The computed maximum_exposure score in INR crore, else None."""
    for score in scores:
        if score.score_id == "maximum_exposure" and score.status is ScoreStatus.computed:
            found = re.search(r"\d+(?:\.\d+)?", (score.value_display or "").replace(",", ""))
            return Decimal(found.group(0)) if found else None
    return None


def exposure_not_evaluable(scores: list[ScoreResult]) -> str:
    """Why the maximum_exposure score has no value although it was computed, else empty."""
    for score in scores:
        if (
            score.score_id == "maximum_exposure"
            and score.status is ScoreStatus.computed
            and not score.value_display
        ):
            return score.caution or "the maximum exposure is not evaluable"
    return ""


def _amount(score: ScoreResult, slot: str) -> str:
    item = next((i for i in score.inputs if i.slot == slot), None)
    if item is None:
        return ""
    unit = item.unit.split(" x ")[0].strip()
    value = f"{item.value.normalize():f}"
    if unit.upper().startswith("INR "):
        return f"INR {value} {unit[4:]}"
    return f"{value} {unit}".strip()


def no_exposure_sentence(scores: list[ScoreResult]) -> str:
    """The sentence for a maximum exposure of zero: the grade that permits none, else empty."""
    if max_exposure_crore(scores) != 0:
        return ""
    exposure = next(s for s in scores if s.score_id == "maximum_exposure")
    grade = next(
        (s for s in scores if s.score_id == "internal_risk_grade" and s.value_display), None
    )
    at = f" at internal risk grade {grade.value_display}" if grade else ""
    amount = _amount(exposure, "proposed_exposure")
    proposed = f"the proposed {amount}" if amount else "the proposed exposure"
    return f"The policy permits no exposure{at}, so {proposed} cannot be sanctioned."


def exposure_limit_note(scores: list[ScoreResult]) -> str:
    """The sentence replacing the proposed limit when there is none to state, else empty."""
    reason = exposure_not_evaluable(scores)
    if reason:
        return f"The proposed limit could not be computed: {reason.rstrip('.')}."
    return no_exposure_sentence(scores)


def enforce_policy_floor(
    recommendation: Recommendation, results: list[RuleResult]
) -> tuple[Recommendation, DecisionOverride]:
    """Raise a too-lenient decision to the floor; return the recommendation and the audit record."""
    floor, binding = policy_floor(results)
    model_decision = recommendation.decision
    record = DecisionOverride(
        model_decision=model_decision,
        final_decision=model_decision,
        floor=floor,
        rule_ids=[result.rule_id for result in binding],
        model_headline=recommendation.headline,
        headline=recommendation.headline,
    )
    if DECISION_RANK[model_decision] >= DECISION_RANK[floor]:
        return recommendation, record
    headline = floor_headline(floor, binding)
    conditions = (
        [
            *recommendation.conditions,
            *[r.message for r in binding if r.message not in recommendation.conditions],
        ]
        if floor is Decision.approve_with_conditions
        else []
    )
    note = (
        f"The policy rule engine overrode the model's decision '{model_decision.value}' to "
        f"'{floor.value}' because of rule(s) {', '.join(record.rule_ids)}."
    )
    changed = recommendation.model_copy(
        update={
            "decision": floor,
            "headline": headline,
            "proposed_limit": recommendation.proposed_limit
            if floor is Decision.approve_with_conditions
            else None,
            "conditions": conditions,
            "confidence_note": " ".join(filter(None, [recommendation.confidence_note, note])),
        }
    )
    record = record.model_copy(
        update={"overridden": True, "final_decision": floor, "headline": headline}
    )
    return changed, record


def _inputs_text(result: RuleResult) -> str:
    return ", ".join(
        f"{item.slot} {item.value:f}{' ' + item.unit if item.unit else ''}"
        for item in result.inputs
    )


def rule_reason(result: RuleResult) -> KeyReason:
    """A `policy_rule` reason stating a failing or caution rule from its message and inputs."""
    word = "not met" if result.status is RuleStatus.fail else "in the caution zone"
    inputs = f" (inputs: {_inputs_text(result)})" if result.inputs else ""
    fact_ids = [
        fact_id
        for item in result.inputs
        for fact_id in [item.fact_id, *item.derived_from]
        if fact_id
    ]
    citations = (
        [PolicyCitation(section_id=result.policy_section_id)] if result.policy_section_id else []
    )
    return KeyReason(
        text=f"{result.name} is {word}: {result.message}{inputs}",
        kind="policy_rule",
        policy_citations=citations,
        fact_ids=list(dict.fromkeys(fact_ids)),
        score_ids=list(result.score_ids),
        rule_ids=[result.rule_id],
    )


def missing_rule_reasons(
    recommendation: Recommendation, results: list[RuleResult]
) -> list[KeyReason]:
    """Reasons for failing or caution rules that no existing reason cites by rule id."""
    cited = {rule_id for reason in recommendation.key_reasons for rule_id in reason.rule_ids}
    return [
        rule_reason(result)
        for result in results
        if result.status in (RuleStatus.fail, RuleStatus.caution) and result.rule_id not in cited
    ]


def unevaluated_note(results: list[RuleResult]) -> str:
    """One sentence naming the rules that could not be evaluated, or an empty string."""
    names = [result.rule_id for result in results if result.status is RuleStatus.not_evaluable]
    if not names:
        return ""
    return (
        f"{len(names)} policy rule(s) could not be evaluated for lack of inputs: "
        f"{', '.join(names)}."
    )
