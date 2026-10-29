"""Read and write a bank's folder: policy.md, scores.yaml, approval.json and policy.lean.

`load_bank` turns the folder `banks/<bank_id>/` into one `BankPolicy`; the Lean path is set
only when `policy.lean` exists. `save_formalisation` stores a machine-written policy.lean
together with an unapproved `approval.json`, so a human must still review it.
"""

import json
import os
import re
from pathlib import Path

import yaml

from busybee.policy.rules import validate_rule
from busybee.schema.policy import Approval, BankPolicy, Invariant, PolicyRule, ScoreSpec

_TITLE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_VERSION = re.compile(r"\bVersion\s+([0-9][0-9A-Za-z.\-]*?)\.?(?:\s|$)")


def bank_dir(banks_dir: str | Path, bank_id: str) -> Path:
    """Return the folder of one bank."""
    return Path(banks_dir) / bank_id


def write_atomic(path: Path, text: str) -> None:
    """Write text to path via a temporary file and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def load_scores(scores_yaml: str) -> list[ScoreSpec]:
    """Parse the text of scores.yaml into ScoreSpec models."""
    data = yaml.safe_load(scores_yaml) or {}
    return [ScoreSpec.model_validate(item) for item in data.get("scores", [])]


def load_invariants(scores_yaml: str) -> list[Invariant]:
    """Parse the optional top-level `invariants:` list of scores.yaml."""
    data = yaml.safe_load(scores_yaml) or {}
    return [Invariant.model_validate(item) for item in data.get("invariants") or []]


def load_rules(scores_yaml: str, scores: list[ScoreSpec]) -> list[PolicyRule]:
    """Parse and validate the optional top-level `rules:` list of scores.yaml.

    A rule may only read slot names or score ids declared in `scores`, and its expressions must
    parse; anything else raises `RuleError` so a typo never reaches Lean.
    """
    data = yaml.safe_load(scores_yaml) or {}
    rules = [PolicyRule.model_validate(item) for item in data.get("rules") or []]
    known = {spec.score_id for spec in scores} | {
        slot.slot for spec in scores for slot in spec.inputs
    }
    for rule in rules:
        validate_rule(rule, known)
    return rules


def load_bank(banks_dir: str | Path, bank_id: str) -> BankPolicy:
    """Load policy.md, scores.yaml, approval.json and the Lean path of a bank."""
    folder = bank_dir(banks_dir, bank_id)
    policy_md = (folder / "policy.md").read_text(encoding="utf-8")
    scores_text = (folder / "scores.yaml").read_text(encoding="utf-8")
    scores = load_scores(scores_text)
    approval_path = folder / "approval.json"
    approval = (
        Approval.model_validate(json.loads(approval_path.read_text(encoding="utf-8")))
        if approval_path.is_file()
        else Approval()
    )
    lean_path = folder / "policy.lean"
    title = _TITLE.search(policy_md)
    version = _VERSION.search(policy_md)
    return BankPolicy(
        bank_id=bank_id,
        name=title.group(1) if title else bank_id,
        version=version.group(1) if version else "",
        policy_md=policy_md,
        scores=scores,
        invariants=load_invariants(scores_text),
        rules=load_rules(scores_text, scores),
        lean_path=str(lean_path) if lean_path.is_file() else None,
        approval=approval,
    )


def save_formalisation(folder: str | Path, source: str, generated_by: str) -> Path:
    """Write policy.lean and an unapproved approval.json for a machine-written formalisation."""
    target = Path(folder)
    text = source if source.endswith("\n") else source + "\n"
    write_atomic(target / "policy.lean", text)
    approval = Approval(
        approved=False,
        notes="machine-generated Lean formalisation awaiting human review",
        generated_by=generated_by,
    )
    write_atomic(target / "approval.json", approval.model_dump_json(indent=2) + "\n")
    return target / "policy.lean"
