"""Run the inference stage: write, validate, quantify, repair, independently check, and save.

Inferences whose Lean claim stays false after the repair retries are left out of
`inferences.json` and listed in `inferences_dropped.json`.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from busybee.infer.independent_check import independent_check
from busybee.infer.make_inferences import (
    make_inference_drafts,
    to_inference,
)
from busybee.infer.prompts import InferenceDraft
from busybee.infer.quantify import quantify_inference
from busybee.infer.repair import drop_note, failure_text, repair_inference, settle_failure
from busybee.llm import Provider
from busybee.schema.facts import VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Inference
from busybee.verify.conflicts import is_conflicted

logger = logging.getLogger(__name__)


def _read_models[ModelT](path: Path, model: type[ModelT]) -> list[ModelT]:
    """Read a model list, treating a missing optional input file as an empty list."""
    if not path.is_file():
        return []
    return read_models(path, model)


def _config_run_id(cfg: Any, root: Path) -> str:
    """Return the run id from a config object or mapping, falling back to the directory."""
    value = cfg.get("run_id") if isinstance(cfg, dict) else getattr(cfg, "run_id", None)
    return str(value or root.name or "infer")


async def _quantify_draft(
    inference: Inference,
    draft: InferenceDraft,
    facts: list[VerifiedFact],
    lean_dir: Path,
    run_id: str,
    provider: Provider,
) -> Inference | None:
    """Quantify one inference, repair a failing claim with the model, and settle what remains.

    Returns None when Lean showed the claim false even after the repairs.
    """
    if not inference.quantitative or draft.lean_claim is None:
        return inference
    result = await quantify_inference(
        inference,
        draft.lean_claim,
        facts,
        output_dir=lean_dir,
        run_id=run_id,
    )
    if failure_text(result):
        result = await repair_inference(
            result, draft.lean_claim, facts, provider, output_dir=lean_dir, run_id=run_id
        )
    return result


async def run_infer(
    workspace_dir: str | Path,
    cfg: Any,
    provider: Provider,
) -> list[Inference]:
    """Produce inferences.json from verified facts and optional score results."""
    root = Path(workspace_dir)
    facts = [
        fact
        for fact in _read_models(root / "verified_facts.json", VerifiedFact)
        if not is_conflicted(fact)
    ]
    scores = _read_models(root / "scores.json", ScoreResult)
    output_path = root / "inferences.json"
    if not facts:
        logger.warning("no verified facts; writing an empty inference list")
        write_models_atomic(output_path, [])
        return []
    drafts = await make_inference_drafts(facts, scores, provider)
    inferences = [to_inference(draft, number) for number, draft in enumerate(drafts, start=1)]
    run_id = _config_run_id(cfg, root)
    lean_dir = root / "lean"
    attempted = await asyncio.gather(
        *(
            _quantify_draft(inference, draft, facts, lean_dir, run_id, provider)
            for inference, draft in zip(inferences, drafts, strict=True)
        )
    )
    settled = [(result, settle_failure(result)) for result in attempted]
    dropped = [drop_note(result) for result, kept in settled if kept is None]
    if dropped:
        logger.warning("dropping %d inference(s) whose Lean claim is false", len(dropped))
    write_models_atomic(root / "inferences_dropped.json", dropped)
    quantified = [kept for _, kept in settled if kept is not None]
    checked = await independent_check(quantified, facts, provider)
    write_models_atomic(output_path, checked)
    return checked
