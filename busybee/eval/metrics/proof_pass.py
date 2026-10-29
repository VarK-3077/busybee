"""Proof pass rate: the share of Lean artifacts (scores and quantitative inferences) that compile.

Artifacts are collected from each score result's `lean` and each inference's `lean`; an
artifact passes when its `compile.ok` is true, and one never compiled counts as failing.
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from busybee.schema.lean import LeanArtifact
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Inference

from .common import ratio


class ProofPassResult(BaseModel):
    """Proof pass rate and the ids of artifacts that failed."""

    proof_pass: float | None = None
    passed: int = 0
    total: int = 0
    failed: list[str] = Field(default_factory=list)


def lean_artifacts(
    scores: Sequence[ScoreResult], inferences: Sequence[Inference]
) -> list[LeanArtifact]:
    """Collect every attached Lean artifact in report order."""
    found = [s.lean for s in scores if s.lean is not None]
    found.extend(i.lean for i in inferences if i.lean is not None)
    return found


def compute_proof_pass(
    scores: Sequence[ScoreResult], inferences: Sequence[Inference]
) -> ProofPassResult:
    """Return the compile success rate over score and inference artifacts."""
    artifacts = lean_artifacts(scores, inferences)
    failed = [a.artifact_id for a in artifacts if a.compile is None or not a.compile.ok]
    return ProofPassResult(
        proof_pass=ratio(len(artifacts) - len(failed), len(artifacts)),
        passed=len(artifacts) - len(failed),
        total=len(artifacts),
        failed=failed,
    )
