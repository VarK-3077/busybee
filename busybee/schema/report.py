"""Recommendation, report sections, concerns, audit block, and the final Report."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .documents import Document
from .facts import FactCategory, VerifiedFact
from .lean import LeanArtifact
from .policy import RuleResult, ScoreResult


class Decision(StrEnum):
    """The possible credit recommendations."""

    approve = "approve"
    approve_with_conditions = "approve_with_conditions"
    decline = "decline"
    refer = "refer"
    reduce_or_decline = "reduce_or_decline"


class PolicyCitation(BaseModel):
    """A pointer to the bank-policy section (and clause quote) a reason rests on."""

    section_id: str
    heading: str = ""
    quote: str = ""


class KeyReason(BaseModel):
    """A recommendation reason with a verdict, its kind, and the evidence behind it."""

    text: str
    kind: Literal["policy_rule", "hard_fact", "inference"] = "hard_fact"
    policy_citations: list[PolicyCitation] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    score_ids: list[str] = Field(default_factory=list)
    inference_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """The decision, an actionable headline, conditions, and evidence-linked reasons."""

    decision: Decision
    headline: str = ""
    proposed_limit: str | None = None
    conditions: list[str] = Field(default_factory=list)
    key_reasons: list[KeyReason] = Field(default_factory=list)
    confidence_note: str | None = None


class FactGroup(BaseModel):
    """A report group of facts sharing one category."""

    category: FactCategory = FactCategory.other
    fact_ids: list[str] = Field(default_factory=list)


class Inference(BaseModel):
    """A section-3 judgement derived from verified facts."""

    inference_id: str
    opinion: str
    fact_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0
    quantitative: bool = False
    lean: LeanArtifact | None = None


class Concern(BaseModel):
    """An open question raised by the adversary stage."""

    concern_id: str
    opinion: str
    fact_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""
    query_used: str = ""
    found: bool = False
    severity: str = ""
    dropped_reason: str = ""


class DecisionOverride(BaseModel):
    """Record of the policy rule engine replacing a decision more lenient than its floor."""

    overridden: bool = False
    model_decision: Decision
    final_decision: Decision
    floor: Decision
    rule_ids: list[str] = Field(default_factory=list)
    model_headline: str = ""
    headline: str = ""


class AuditBlock(BaseModel):
    """Provenance for the whole run, shown alongside the report."""

    models: dict[str, str] = Field(default_factory=dict)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    llm_calls: int = 0
    policy_version: str = ""
    lean_toolchain: str = ""
    generated_at: datetime | None = None
    decision_override: DecisionOverride | None = None


class Report(BaseModel):
    """The complete report contract rendered to HTML."""

    run_id: str
    company: str = ""
    bank_id: str = ""
    policy_approved: bool = False
    recommendation: Recommendation | None = None
    facts: dict[str, VerifiedFact] = Field(default_factory=dict)
    fact_groups: list[FactGroup] = Field(default_factory=list)
    scores: list[ScoreResult] = Field(default_factory=list)
    rule_results: list[RuleResult] = Field(default_factory=list)
    inferences: list[Inference] = Field(default_factory=list)
    concerns: list[Concern] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    audit: AuditBlock = Field(default_factory=AuditBlock)
