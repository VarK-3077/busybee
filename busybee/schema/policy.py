"""Bank policy, score specifications, input bindings, and score results."""

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .lean import LeanArtifact


class ScoreStatus(StrEnum):
    """Whether a score could be computed, and whether Lean agreed."""

    computed = "computed"
    not_computable = "not_computable"
    lean_failed = "lean_failed"


class SlotJudgement(BaseModel):
    """How a slot that no single fact states (a flag or a count) is judged from the facts.

    `rubric_headings` name the policy sections whose text is the rubric, `keywords` pick the
    candidate facts, and `answer` says whether the value is a 0/1 flag or a non-negative count.
    """

    rubric_headings: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    answer: Literal["flag", "count"] = "flag"


class InputSlot(BaseModel):
    """A named input required by a score, with its unit and integer scale.

    `definition` and `derive_from` tell the binder how to build a slot no fact states (a
    combination of signed fact numbers). `mapping` makes the slot a categorical lookup (a
    rating grade to its index), `judge` makes it a policy judgement over candidate facts,
    `fallback_slot` and `fallback_note` name another slot whose bound fact stands in when this
    one stays unbound, and `run_parameter` names the bank input (a `busybee run` option) that
    supplies it.
    """

    slot: str
    description: str = ""
    unit: str = ""
    scale: int = 1
    definition: str = ""
    derive_from: list[str] = Field(default_factory=list)
    mapping: dict[str, int] = Field(default_factory=dict)
    judge: SlotJudgement | None = None
    fallback_slot: str = ""
    fallback_note: str = ""
    run_parameter: str = ""


class GradeRule(BaseModel):
    """A grade label and the natural-language condition that earns it."""

    label: str
    condition_text: str = ""


class ScoreSpec(BaseModel):
    """The machine-readable definition of one bank score."""

    score_id: str
    name: str
    description: str = ""
    unit: str = ""
    value_scale: int = 1
    value_meaning: str = ""
    inputs: list[InputSlot] = Field(default_factory=list)
    lean_function: str = ""
    grades: list[GradeRule] = Field(default_factory=list)


class Invariant(BaseModel):
    """A sanity rule over bound slot values, e.g. `net_debt <= total_debt`."""

    name: str
    expression: str
    message: str = ""


class RuleOutcome(StrEnum):
    """What a policy rule forces when not met; `caution` and `pass_required` only condition."""

    decline = "decline"
    refer = "refer"
    caution = "caution"
    pass_required = "pass_required"


class PolicyRule(BaseModel):
    """A hard policy rule over slot names and score ids, e.g. `100 * cfads >= 125 * debt_service`.

    `expression` is the condition that must hold: integer cross-multiplied comparisons joined by
    `and` / `or` (`and` binds tighter). `caution_expression`, when given, is true inside the
    caution zone and is only consulted while `expression` holds. `policy_section` is the
    section number written in policy.md (for example "4"). `measure` names the ratio the rule
    tests (for example "Net debt / EBITDA"), computed as `measure_numerator` over
    `measure_denominator` (slot expressions) shown as `measure_unit` ("x" or "%"), with
    `limit_text` the minimum standard in words ("at most 4.5x").
    """

    rule_id: str
    name: str
    expression: str
    outcome: RuleOutcome
    policy_section: str = ""
    message: str = ""
    caution_expression: str = ""
    measure: str = ""
    measure_numerator: str = ""
    measure_denominator: str = ""
    measure_unit: str = "x"
    limit_text: str = ""


class Approval(BaseModel):
    """A bank's approval state for its formalised policy."""

    approved: bool = False
    by: str | None = None
    date: str | None = None
    notes: str = ""
    generated_by: str | None = None


class BankPolicy(BaseModel):
    """A bank filesystem loaded into one model."""

    bank_id: str
    name: str = ""
    version: str = ""
    policy_md: str = ""
    scores: list[ScoreSpec] = Field(default_factory=list)
    invariants: list[Invariant] = Field(default_factory=list)
    rules: list[PolicyRule] = Field(default_factory=list)
    lean_path: str | None = None
    approval: Approval = Field(default_factory=Approval)


class BoundTerm(BaseModel):
    """One signed term of a derived slot: the fact number it read and its scaled contribution."""

    component: str
    fact_id: str
    value: Decimal
    unit: str = ""
    sign: int = 1
    value_scaled: int = 0


class BoundInput(BaseModel):
    """A score input slot bound to a verified fact and its scaled integer value.

    `missing` lists the components of a derived slot that no fact supplied (the value is
    computed without them and `caution` says so); `terms` are the signed terms it was summed from.
    """

    slot: str
    fact_id: str
    value: Decimal
    unit: str = ""
    value_scaled: int = 0
    derived_from: list[str] = Field(default_factory=list)
    note: str = ""
    caution: str = ""
    missing: list[str] = Field(default_factory=list)
    terms: list[BoundTerm] = Field(default_factory=list)


class ScoreResult(BaseModel):
    """The display value, grade, and Lean evidence for one score.

    `bands` names each scoring band that awarded no points because an input it reads is a proxy
    or lacks components (band -> "not evaluable (proxy)"), and `caution` says so in one line.
    """

    score_id: str
    status: ScoreStatus = ScoreStatus.computed
    inputs: list[BoundInput] = Field(default_factory=list)
    value_display: str | None = None
    grade: str | None = None
    lean: LeanArtifact | None = None
    unbound: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    caution: str = ""
    bands: dict[str, str] = Field(default_factory=dict)


class RuleStatus(StrEnum):
    """The Lean-computed result of one policy rule."""

    passed = "pass"
    caution = "caution"
    fail = "fail"
    not_evaluable = "not_evaluable"


class RuleResult(BaseModel):
    """One policy rule evaluated by Lean over the bound inputs of this run.

    `basis` is the statement basis ("consolidated" or "standalone") the inputs were bound on and
    `caution_reason` why a rule that holds is shown as `caution` (a missing component, a proxy,
    mixed bases). `measure`, `computed_value` and `threshold` give the tested ratio, its
    computed value ("4.71x") and the minimum standard ("at most 4.5x") for compose to name.

    `inputs` are the bound slots the rule reads (a score read by a rule appears as an input with
    an empty `fact_id` and the score id in `score_ids`). A rule with unbound inputs is
    `not_evaluable` and `unbound` maps each missing slot to the reason.
    """

    rule_id: str
    name: str
    status: RuleStatus
    outcome: RuleOutcome
    message: str = ""
    expression: str = ""
    inputs: list[BoundInput] = Field(default_factory=list)
    score_ids: list[str] = Field(default_factory=list)
    unbound: dict[str, str] = Field(default_factory=dict)
    policy_section: str = ""
    policy_section_id: str = ""
    lean: LeanArtifact | None = None
    basis: str = ""
    caution_reason: str = ""
    measure: str = ""
    computed_value: str = ""
    threshold: str = ""


class PolicyEvaluation(BaseModel):
    """Every policy rule result of a run, written to `policy_eval.json`."""

    rules: list[RuleResult] = Field(default_factory=list)
