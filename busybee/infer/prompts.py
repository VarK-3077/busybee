"""System prompt and response models for the section-3 inference writer."""

from pydantic import BaseModel, Field, field_validator

from busybee.llm import Message, Role

TASK = "infer"
MAX_INFERENCES = 8
DEFAULT_CONFIDENCE = 0.5
LOW_CONFIDENCE = 0.2
_LOW_CONFIDENCE_WORDS = {"low": LOW_CONFIDENCE, "medium": 0.6, "high": 0.85}


def normalise_confidence(value: object) -> float:
    """Convert a confidence word, percentage, or fraction to a number in [0, 1]."""
    if value is None:
        return DEFAULT_CONFIDENCE
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _LOW_CONFIDENCE_WORDS:
            return _LOW_CONFIDENCE_WORDS[word]
        try:
            value = float(word)
        except ValueError:
            return DEFAULT_CONFIDENCE
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE
    if number > 1:
        number = number / 100 if number <= 100 else 1.0
    return max(0.0, min(1.0, number))


class LeanClaim(BaseModel):
    """A Lean sketch mapping variable names to fact ids and an arithmetic claim."""

    facts: dict[str, str] = Field(default_factory=dict)
    claim: str = ""


class InferenceDraft(BaseModel):
    """One LLM-written inference before code validation and Lean quantification."""

    opinion: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = DEFAULT_CONFIDENCE
    quantitative: bool = False
    lean_claim: LeanClaim | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _parse_confidence(cls, value: object) -> float:
        """Accept a numeric or verbal confidence from the model."""
        return normalise_confidence(value)


class InferenceOutput(BaseModel):
    """The inference writer's structured reply."""

    inferences: list[InferenceDraft] = Field(default_factory=list)


SYSTEM_PROMPT = """You are a credit officer writing section 3 of a credit review.

From the verified facts and score results supplied by the user, produce at most 8 short
inferences a credit officer would draw about the borrower. Cover the important trends, risks,
and repayment capacity; do not repeat a fact verbatim as an inference.

Every inference must have:
- opinion: one sentence stating the judgement.
- fact_ids: the ids of the verified facts the judgement rests on. Use only ids from the list.
- reasoning: two to four sentences that reference only those facts. Do not introduce outside
  knowledge, management guidance, market assumptions, or unlisted numbers.
- When the reasoning quotes a ratio the company itself reports (interest coverage, DSCR, net
  debt/EBITDA, current ratio, debt/equity), say it is the company-reported figure, state its
  basis if the source gives one (consolidated or standalone, and how it is defined), and never
  present it as the policy ratio, which the policy rules compute separately.
- confidence: a number from 0 to 1 reflecting the strength of the evidence.
- quantitative: true only when the judgement is an arithmetic or threshold comparison that can
  be checked in Lean.

For a quantitative inference also include lean_claim:
- facts: an object mapping each Lean variable name used in the claim to the fact that
  supplies its value, for example {"net_debt": "F012", "ebitda": "F013"}. A plain fact id
  uses the fact's first listed number; to use another number of that fact write the id, a
  hash sign and the number exactly as listed, for example "F046#1.25" for the 1.25 times
  covenant limit of F046, whose first number 1.78 is the actual ratio. Two variables must
  never name the same number.
- claim: a closed integer arithmetic statement over those variable names, written with
  comparison operators such as <=, <, >=, > or ==, for example "2 * net_debt <= 7 * ebitda".
  A whole side of a comparison that is a bare integer, such as the 1 in
  "interest_coverage < 1" or the 0 in "net_loss < 0", is read in the natural unit of the other
  side: crore for money (never lakh), percent for percentages, times for ratios.
  Never write a decimal literal such as 1.25: map that number to a variable instead (every
  threshold you compare against must come from a fact). Do not use division, functions,
  hypotheses, or variable names that are not keys in facts. Write a comparison chain as separate
  comparisons joined by &&, never "a < b < c". All variables compared with each other must be
  in the same unit (do not compare a crore amount with a ratio or a percentage).

Return JSON with one key, inferences, holding the list of inference objects. Order the most
important inferences first and use no more than 8."""


def build_messages(compact_fact_list: str) -> list[Message]:
    """Build the system and user messages carrying the compact fact list."""
    user = f"Verified facts and scores (id | category | statement | numbers):\n{compact_fact_list}"
    return [
        Message(role=Role.system, content=SYSTEM_PROMPT),
        Message(role=Role.user, content=user),
    ]


def inference_messages(compact_fact_list: str) -> list[Message]:
    """Alias for build_messages used by callers that name the stage explicitly."""
    return build_messages(compact_fact_list)
