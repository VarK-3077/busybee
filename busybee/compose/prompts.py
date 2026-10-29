"""Build the recommendation prompt and the structured model the LLM must return."""

from pydantic import BaseModel, Field

from busybee.llm.messages import Message, Role
from busybee.schema.policy import ScoreSpec
from busybee.schema.report import Decision, KeyReason

from .inputs import ComposeInputs
from .policy_floor import policy_floor

TASK = "compose"

SECTION_CHAR_LIMIT = 1500
SECTIONS_CHAR_BUDGET = 30000

SYSTEM_INSTRUCTIONS = """You are a senior credit officer at a bank. Decide whether to grant
the borrower a credit line. Choose exactly one decision: approve, approve_with_conditions,
decline, refer, or reduce_or_decline (reduce the credit line or decline, used when a
minimum standard of the policy is failed).

The headline is the decision as an action sentence that names the amount, for example
"Approve a working-capital limit of INR 60.0 crore", "Decline the facility", or "Reduce the
credit limit to INR 40 crore". Follow the bank policy's sizing rule when the inputs support it
and put the same amount in proposed_limit (short string with currency and unit); use null for
proposed_limit and name no amount when the sizing inputs are unavailable. Do not invent a limit.

Give conditions only when they follow from the policy or the recommendation.

The "Policy rule results" section lists bank-policy rules that Lean has already evaluated; their
status is binding and must never be contradicted. The line "Policy-implied minimum decision" is a
floor: order the decisions approve < approve_with_conditions < refer < reduce_or_decline <
decline, and your decision must be at least as strict as the floor (a more lenient decision
is overridden by code). Every
rule whose status is fail or caution needs its own "policy_rule" reason that lists the rule id
in rule_ids and also cites its policy section, fact_ids and score_ids; a rule marked
not_evaluable gets no verdict.

Give 3 to 8 key reasons. Each reason has a kind:
- "policy_rule": a bank-policy test applied to the borrower. Cite at least one policy section id
  in policy_citations (section_id, and quote = a short verbatim clause copied from that section),
  and cite the fact_ids / score_ids the test rests on, plus rule_ids for a listed policy rule.
- "hard_fact": a documented fact about the borrower (cash flow, revenue, rating, litigation).
  Cite fact_ids, and score_ids when a score is quoted.
- "inference": a forward-looking judgement or guess. Cite inference_ids.
Write at least one reason of each kind whenever the inputs allow it.

Every reason is one sentence that states a verdict with the actual numbers, for example
"Net debt/EBITDA of 2.7x is within the 3.5x policy cap", "Interest coverage 3.4x exceeds the
2.5x minimum", or "Revenue grew 10.1% to INR 931.2 crore, above the policy's positive-growth
requirement". Never write a bare topic such as "Revenue is documented". Never invent ids; cite
only ids that appear in the evidence, and make sure each id actually supports the sentence.

Each score is listed with its value, grade and what they mean; read the value and grade only
as described there (for example a limit-type value is an amount, never a pass/fail flag).

Write a one-sentence confidence note. If there are open concerns, mention them explicitly.
Use only the supplied policy and evidence. Do not mention sources that are not in the evidence.
"""


class RecommendationOutput(BaseModel):
    """The LLM's structured recommendation before code-side id checking."""

    decision: Decision
    headline: str = ""
    proposed_limit: str | None = None
    conditions: list[str] = Field(default_factory=list)
    key_reasons: list[KeyReason] = Field(default_factory=list)
    confidence_note: str = ""


def build_system_prompt(inputs: ComposeInputs | None = None) -> str:
    """Return the system prompt, including the bank policy summary when available."""
    if inputs is None or not inputs.policy_summary or inputs.policy_sections:
        return SYSTEM_INSTRUCTIONS
    version = inputs.policy.version or "unknown"
    return (
        f"{SYSTEM_INSTRUCTIONS}\n"
        f"Bank policy summary ({inputs.policy.bank_id}, version {version}):\n"
        f"{inputs.policy_summary}"
    )


def _fact_lines(inputs: ComposeInputs) -> list[str]:
    return [f"- {fact.fact_id} [{fact.category}] {fact.statement}" for fact in inputs.facts]


def _score_meaning_lines(spec: ScoreSpec) -> list[str]:
    """Indented lines that tell the model what a score's value and grade mean."""
    lines = [f"    {spec.name}: {spec.description}".rstrip(": ")]
    unit = f" in {spec.unit}" if spec.unit else ""
    if spec.value_meaning:
        lines.append(f"    value{unit}: {spec.value_meaning}")
    if spec.grades:
        grades = "; ".join(f'"{grade.label}" = {grade.condition_text}' for grade in spec.grades)
        lines.append(f"    grade: {grades}")
    return lines


def _score_lines(inputs: ComposeInputs) -> list[str]:
    specs = {spec.score_id: spec for spec in inputs.score_specs}
    lines = []
    for score in inputs.scores:
        value = score.value_display or score.status.value
        grade = f", grade {score.grade}" if score.grade else ""
        lines.append(f"- {score.score_id}: {value}{grade} ({score.status.value})")
        if score.score_id in specs:
            lines.extend(_score_meaning_lines(specs[score.score_id]))
    return lines


def _rule_lines(inputs: ComposeInputs) -> list[str]:
    """One line per evaluated policy rule, then the policy-implied minimum decision."""
    lines = []
    for rule in inputs.rule_results:
        values = ", ".join(f"{item.slot}={item.value:f}" for item in rule.inputs)
        detail = (
            f"cannot be evaluated, unbound: {', '.join(rule.unbound)}"
            if rule.status.value == "not_evaluable"
            else f"inputs {values}"
            if values
            else "no inputs"
        )
        section = f"policy section {rule.policy_section_id}" if rule.policy_section_id else "policy"
        lines.append(
            f"- {rule.rule_id} | {rule.name} | {rule.status.value} | outcome if not met "
            f"{rule.outcome.value} | {detail} | {section} | {rule.message}"
        )
    if inputs.rule_results:
        floor, binding = policy_floor(inputs.rule_results)
        ids = ", ".join(rule.rule_id for rule in binding) or "no rule"
        lines.append(f"Policy-implied minimum decision: {floor.value} (from {ids})")
    return lines


def _inference_lines(inputs: ComposeInputs) -> list[str]:
    return [
        f"- {inference.inference_id}: {inference.opinion} "
        f"(facts {', '.join(inference.fact_ids) or 'none'}; confidence {inference.confidence:.2f})"
        for inference in inputs.inferences
    ]


def _concern_lines(inputs: ComposeInputs) -> list[str]:
    return [
        f"- {concern.concern_id}: {concern.opinion} "
        f"(facts {', '.join(concern.fact_ids) or 'none'}; "
        f"{'open' if not concern.found else 'answered'})"
        for concern in inputs.concerns
    ]


def _document_lines(inputs: ComposeInputs) -> list[str]:
    return [f"- {document.doc_id}: {document.title}" for document in inputs.documents]


def _policy_section_lines(inputs: ComposeInputs) -> list[str]:
    """Render policy sections as id, heading and truncated text within a total budget."""
    lines: list[str] = []
    remaining = SECTIONS_CHAR_BUDGET
    for section in inputs.policy_sections:
        text = section.text
        if len(text) > SECTION_CHAR_LIMIT:
            text = text[:SECTION_CHAR_LIMIT].rstrip() + " [...]"
        entry = f"[{section.section_id}] {section.heading}\n{text}".rstrip()
        if len(entry) > remaining:
            break
        remaining -= len(entry)
        lines.append(entry)
    return lines


def _section(title: str, lines: list[str], empty: str) -> str:
    body = "\n".join(lines) if lines else empty
    return f"{title}\n{body}"


def build_evidence(inputs: ComposeInputs) -> str:
    """Render the workspace evidence as a compact, id-labelled user message."""
    return "\n\n".join(
        [
            _section("Policy sections", _policy_section_lines(inputs), "(none)"),
            _section("Facts", _fact_lines(inputs), "(none)"),
            _section("Scores", _score_lines(inputs), "(none)"),
            _section("Policy rule results", _rule_lines(inputs), "(none)"),
            _section("Inferences", _inference_lines(inputs), "(none)"),
            _section("Open concerns", _concern_lines(inputs), "(none)"),
            _section("Documents", _document_lines(inputs), "(none)"),
            "Return one JSON object matching the schema.",
        ]
    )


def build_messages(inputs: ComposeInputs) -> list[Message]:
    """Build the system and user messages for the recommendation call."""
    return [
        Message(role=Role.system, content=build_system_prompt(inputs)),
        Message(role=Role.user, content=build_evidence(inputs)),
    ]
