"""Load the workspace outputs and bank policy that compose needs, tolerating absent files.

Conflicted facts are kept apart (`conflicted_facts`) so the recommendation never cites them, and
the concerns of `conflicts.json` (written by verify) are merged after the adversary's concerns.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from busybee.policy.bank_fs import load_scores
from busybee.policy.policy_sections import PolicySection, split_policy_sections
from busybee.schema.documents import Document
from busybee.schema.facts import VerifiedFact
from busybee.schema.io import read_json, read_model, read_models
from busybee.schema.policy import (
    Approval,
    BankPolicy,
    PolicyEvaluation,
    RuleResult,
    ScoreResult,
    ScoreSpec,
)
from busybee.schema.report import Concern, Inference
from busybee.schema.run import RunConfig
from busybee.verify.conflicts import is_conflicted

POLICY_SUMMARY_LINES = 60


@dataclass(frozen=True)
class ComposeInputs:
    """All evidence available to the recommendation and report assembly."""

    facts: list[VerifiedFact]
    scores: list[ScoreResult]
    inferences: list[Inference]
    concerns: list[Concern]
    documents: list[Document]
    policy: BankPolicy
    policy_summary: str
    policy_sections: list[PolicySection] = field(default_factory=list)
    score_specs: list[ScoreSpec] = field(default_factory=list)
    conflicted_facts: list[VerifiedFact] = field(default_factory=list)
    rule_results: list[RuleResult] = field(default_factory=list)

    @property
    def fact_ids(self) -> set[str]:
        """Return every admitted fact id."""
        return {fact.fact_id for fact in self.facts}

    @property
    def score_ids(self) -> set[str]:
        """Return every available score id."""
        return {score.score_id for score in self.scores}

    @property
    def inference_ids(self) -> set[str]:
        """Return every inference id."""
        return {inference.inference_id for inference in self.inferences}

    @property
    def rule_ids(self) -> set[str]:
        """Return every evaluated policy rule id."""
        return {result.rule_id for result in self.rule_results}

    @property
    def policy_section_ids(self) -> set[str]:
        """Return every citable policy section id."""
        return {section.section_id for section in self.policy_sections}


def policy_summary(policy_md: str, *, max_lines: int = POLICY_SUMMARY_LINES) -> str:
    """Return the first max_lines lines of a policy document."""
    return "\n".join(policy_md.splitlines()[:max_lines]).strip()


def policy_version(policy_md: str) -> str:
    """Return the version token from a policy heading such as 'Version 1.0.'."""
    for line in policy_md.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("version"):
            continue
        words = stripped.split()
        return words[1].rstrip(".") if len(words) > 1 else ""
    return ""


def policy_name(policy_md: str, bank_id: str) -> str:
    """Return the title before the dash of the first Markdown heading."""
    for line in policy_md.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        title = stripped.lstrip("#").strip()
        for separator in (" — ", " - ", " – "):
            if separator in title:
                title = title.split(separator, 1)[0].strip()
                break
        return title or bank_id
    return bank_id


def _read_models_if_present(path: Path, model: type[Any]) -> list[Any]:
    """Read a JSON model array, returning an empty list when the file is absent."""
    return read_models(path, model) if path.exists() else []


def load_approval(bank_dir: Path) -> Approval:
    """Read approval.json, falling back to an unapproved default when absent."""
    path = bank_dir / "approval.json"
    if not path.exists():
        return Approval()
    return Approval.model_validate(read_json(path))


def load_score_specs(banks_dir: str | Path, bank_id: str) -> list[ScoreSpec]:
    """Read the bank's scores.yaml into ScoreSpecs, or nothing when it is absent."""
    path = Path(banks_dir) / bank_id / "scores.yaml"
    return load_scores(path.read_text(encoding="utf-8")) if path.exists() else []


def load_bank_policy(banks_dir: str | Path, bank_id: str) -> BankPolicy:
    """Load the bank's policy text, version, name, and approval state."""
    bank_dir = Path(banks_dir) / bank_id
    policy_path = bank_dir / "policy.md"
    policy_md = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""
    return BankPolicy(
        bank_id=bank_id,
        name=policy_name(policy_md, bank_id),
        version=policy_version(policy_md),
        policy_md=policy_md,
        approval=load_approval(bank_dir),
    )


def load_rule_results(workspace: Path) -> list[RuleResult]:
    """Read policy_eval.json, or no rule results when the scores stage wrote none."""
    path = workspace / "policy_eval.json"
    return read_model(path, PolicyEvaluation).rules if path.exists() else []


def load_compose_inputs(
    workspace_dir: str | Path,
    cfg: RunConfig,
    banks_dir: str | Path,
) -> ComposeInputs:
    """Load all compose inputs from the workspace and the selected bank."""
    workspace = Path(workspace_dir)
    policy = load_bank_policy(banks_dir, cfg.bank_id)
    all_facts = _read_models_if_present(workspace / "verified_facts.json", VerifiedFact)
    return ComposeInputs(
        facts=[fact for fact in all_facts if not is_conflicted(fact)],
        conflicted_facts=[fact for fact in all_facts if is_conflicted(fact)],
        scores=_read_models_if_present(workspace / "scores.json", ScoreResult),
        inferences=_read_models_if_present(workspace / "inferences.json", Inference),
        concerns=[
            *_read_models_if_present(workspace / "concerns.json", Concern),
            *_read_models_if_present(workspace / "conflicts.json", Concern),
        ],
        documents=_read_models_if_present(workspace / "corpus" / "documents.json", Document),
        policy=policy,
        policy_summary=policy_summary(policy.policy_md),
        policy_sections=split_policy_sections(policy.policy_md),
        score_specs=load_score_specs(banks_dir, cfg.bank_id),
        rule_results=load_rule_results(workspace),
    )
