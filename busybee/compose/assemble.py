"""Assemble the final Report from loaded evidence, the recommendation, and the audit."""

from pathlib import Path
from typing import Any

from busybee.schema.documents import Document
from busybee.schema.io import read_json
from busybee.schema.report import AuditBlock, FactGroup, Recommendation, Report
from busybee.schema.run import RunConfig

from .fact_groups import group_facts
from .inputs import ComposeInputs


def _manifest_company(docs_dir: str | Path | None) -> str:
    """Return a top-level company name from manifest.json when one is present."""
    if docs_dir is None:
        return ""
    path = Path(docs_dir) / "manifest.json"
    if not path.exists():
        return ""
    try:
        raw: Any = read_json(path)
    except (OSError, ValueError):
        return ""
    if not isinstance(raw, dict):
        return ""
    for key in ("company", "borrower", "name"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for entry in raw.values():
        if isinstance(entry, dict):
            for key in ("company", "borrower"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def company_name(cfg: RunConfig, documents: list[Document]) -> str:
    """Return the run's company from config, manifest, or the first document title."""
    configured = getattr(cfg, "company", None)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    manifest_company = _manifest_company(cfg.docs_dir)
    if manifest_company:
        return manifest_company
    if documents:
        return documents[0].title
    return ""


def build_report(
    cfg: RunConfig,
    inputs: ComposeInputs,
    recommendation: Recommendation,
    audit: AuditBlock | None = None,
    fact_groups: list[FactGroup] | None = None,
) -> Report:
    """Build the complete Report model from compose's inputs and decision."""
    groups = group_facts(inputs.facts) if fact_groups is None else fact_groups
    return Report(
        run_id=cfg.run_id,
        company=company_name(cfg, inputs.documents),
        bank_id=cfg.bank_id,
        policy_approved=inputs.policy.approval.approved,
        recommendation=recommendation,
        facts={fact.fact_id: fact for fact in [*inputs.facts, *inputs.conflicted_facts]},
        fact_groups=groups,
        scores=inputs.scores,
        rule_results=inputs.rule_results,
        inferences=inputs.inferences,
        concerns=inputs.concerns,
        documents=inputs.documents,
        audit=audit or AuditBlock(),
    )
