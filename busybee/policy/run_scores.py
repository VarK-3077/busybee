"""The `scores` stage: bank policy + verified facts -> Lean-computed `scores.json`.

Steps: load the bank (formalising `policy.lean` with the writer/checker loop when it is
missing), write the bank's run parameters (proposed exposure, projected turnover) into
`verified_facts.json` as `bank_input` facts, sync the policy into the Lake project, bind score
inputs to verified facts (pick, map a rating, judge a flag, derive from terms, compute an
unbound balance-sheet subtotal from printed totals with `subtotals.py`), search the documents
for the facts of slots still unbound (`slot_search.py`, then bind those slots again and the
subtotals once more, and, when facts were added, rebuild every incomplete derived slot from
them with `complete_derived.py`, and finally give a derived slot whose component is another
bound slot, such as the EBITDA of CFADS, that slot's binding with `slot_components.py`, so the
rules below are evaluated on the rebound values), then
check the bank's `invariants` (one binder retry, leftovers become `ScoreResult.warnings`;
from here on `evaluate_bound_scores`, which `tools/replay_scores.py` calls on a saved run),
generate `Scores.lean` twice. Pass one only evaluates, so Lean prints every value and grade;
pass two repeats the file with `decide` theorems pinning those printed results and is the
artifact kept in the report. Scores with unbound slots are `not_computable`; if Lean fails,
the affected scores are `lean_failed` and the failing artifact is kept for the report.

A band of a points score that reads a proxy or incomplete input awards 0 points (`bands.py`):
the score keeps its Lean value without that band, its `caution` names the band and `bands`
marks it "not evaluable (proxy)". A score that is not a sum of bands (a limit computation)
reading such an input is not evaluable instead: no value, grade "Not evaluable", the reason
in its `caution`.

The same file evaluates the bank's policy `rules` (`rules.py`): pass one prints each rule's
status, pass two proves it by `decide`; the results go to `policy_eval.json`
(`PolicyEvaluation`) and a rule with an unbound input is `not_evaluable`.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from busybee.lean.artifact import make_artifact
from busybee.lean.compile import compile_file
from busybee.lean.project import runs_dir, sync_policy_module
from busybee.llm import Provider
from busybee.policy.bands import (
    BAND_NOT_EVALUABLE,
    SCORE_NOT_EVALUABLE,
    ScoreAdjustment,
    excluded_bands,
    not_evaluable_reason,
)
from busybee.policy.bank_fs import bank_dir, load_bank, save_formalisation, write_atomic
from busybee.policy.bank_inputs import read_all_facts, sync_bank_input_facts
from busybee.policy.bind_inputs import BindingResult, bind_inputs
from busybee.policy.complete_derived import complete_derived_slots
from busybee.policy.formalize.loop import formalise
from busybee.policy.generate import build_scores_lean, computable_scores, rule_bindings
from busybee.policy.invariants import enforce_invariants
from busybee.policy.parse_eval import ParsedScore, parse_eval_output
from busybee.policy.policy_sections import split_policy_sections
from busybee.policy.rules import (
    ResolvedRule,
    add_score_inputs,
    build_rule_results,
    parse_rule_statuses,
)
from busybee.policy.scaling import format_score_value
from busybee.policy.slot_components import with_slot_components
from busybee.policy.slot_search import fill_unbound_slots, rebind_slots
from busybee.policy.subtotals import with_subtotals
from busybee.schema.facts import VerifiedFact
from busybee.schema.lean import CompileResult, LeanArtifact
from busybee.schema.policy import (
    BankPolicy,
    BoundInput,
    PolicyEvaluation,
    ScoreResult,
    ScoreSpec,
    ScoreStatus,
)
from busybee.schema.run import RunConfig
from busybee.verify.conflicts import is_conflicted


def load_verified_facts(workspace_dir: Path) -> list[VerifiedFact]:
    """Read verified_facts.json (list, dict, or {"facts": [...]}) minus conflicted facts."""
    return [fact for fact in read_all_facts(workspace_dir) if not is_conflicted(fact)]


async def ensure_policy_lean(
    bank: BankPolicy, workspace_dir: Path, banks_dir: Path, provider: Provider
) -> BankPolicy:
    """Return the bank with a policy.lean, writing an unapproved one first if missing."""
    if bank.lean_path is not None:
        return bank
    result = await formalise(provider, bank, workspace_dir / "formalize")
    save_formalisation(bank_dir(banks_dir, bank.bank_id), result.source, provider.model)
    return load_bank(banks_dir, bank.bank_id)


def _result(
    spec: ScoreSpec,
    status: ScoreStatus,
    bound: list[BoundInput],
    artifact: LeanArtifact | None,
    value: str | None = None,
    grade: str | None = None,
    unbound: dict[str, str] | None = None,
) -> ScoreResult:
    return ScoreResult(
        score_id=spec.score_id,
        status=status,
        inputs=bound,
        value_display=value,
        grade=grade,
        lean=artifact,
        unbound=unbound or {},
    )


def unbound_slots(
    spec: ScoreSpec,
    bound: list[BoundInput],
    reasons: dict[tuple[str, str], str],
    score_ids: set[str],
    ready_ids: set[str],
) -> dict[str, str]:
    """Why each input of a not-computable score is missing, including upstream scores."""
    have = {item.slot for item in bound}
    missing = {}
    for slot in spec.inputs:
        if slot.slot in have or slot.slot in ready_ids:
            continue
        reason = reasons.get((spec.score_id, slot.slot))
        if reason is None and slot.slot in score_ids and slot.slot != spec.score_id:
            reason = f"depends on score {slot.slot}, which is not computable"
        missing[slot.slot] = reason or "not bound"
    return missing


def _pins(parsed: dict[str, ParsedScore], ready: list[ScoreSpec]) -> dict[str, tuple[str, str]]:
    """Printed (value, grade) pairs that are whole numbers, ready to be pinned by theorems."""
    pins = {}
    for spec in ready:
        item = parsed.get(spec.score_id)
        if item and item.value and item.grade and item.value.lstrip("-").isdigit():
            pins[spec.score_id] = (item.value, item.grade)
    return pins


async def _compile_source(path: Path, source: str) -> CompileResult:
    write_atomic(path, source)
    return await compile_file(path)


async def run_scores(
    workspace_dir: Path, cfg: RunConfig, provider: Provider, banks_dir: Path
) -> list[ScoreResult]:
    """Compute every bank score in Lean and write workspace_dir/scores.json."""
    workspace_dir = Path(workspace_dir)
    bank = load_bank(banks_dir, cfg.bank_id)
    bank = await ensure_policy_lean(bank, workspace_dir, Path(banks_dir), provider)
    sync_bank_input_facts(workspace_dir, cfg)
    facts = load_verified_facts(workspace_dir)
    sections = split_policy_sections(bank.policy_md)
    binding = with_subtotals(
        bank.scores, await bind_inputs(provider, bank.scores, facts, sections), facts
    )
    searched = await fill_unbound_slots(workspace_dir, provider, bank.scores, facts, binding)
    if searched.slots:
        facts = load_verified_facts(workspace_dir)
        binding = await rebind_slots(
            provider, bank.scores, facts, binding, searched.slots, sections
        )
        binding = with_subtotals(bank.scores, binding, facts)
    if searched.added:
        binding = complete_derived_slots(bank.scores, binding, facts)
    binding = with_slot_components(bank.scores, binding, facts)
    return await evaluate_bound_scores(workspace_dir, cfg, bank, provider, facts, binding)


async def evaluate_bound_scores(
    workspace_dir: Path,
    cfg: RunConfig,
    bank: BankPolicy,
    provider: Provider,
    facts: list[VerifiedFact],
    binding: BindingResult,
) -> list[ScoreResult]:
    """Check invariants, compute the ready scores and rules in Lean, write both result files."""
    fact_index = {fact.fact_id: fact for fact in facts}
    binding.bound, warnings = await enforce_invariants(
        provider, bank.scores, bank.invariants, facts, binding.bound
    )
    ready = computable_scores(bank.scores, binding.bound)
    ready_ids = {spec.score_id for spec in ready}
    results: dict[str, ScoreResult] = {
        spec.score_id: _result(
            spec,
            ScoreStatus.not_computable,
            binding.bound.get(spec.score_id, []),
            None,
            unbound=unbound_slots(
                spec,
                binding.bound.get(spec.score_id, []),
                binding.unbound,
                {item.score_id for item in bank.scores},
                ready_ids,
            ),
        )
        for spec in bank.scores
        if spec.score_id not in ready_ids
    }
    slot_reasons = {slot: reason for (_, slot), reason in binding.unbound.items()}
    resolved = rule_bindings(bank.rules, bank.scores, binding.bound, slot_reasons)
    evaluable = [rule for rule in bank.rules if not resolved[rule.rule_id].missing]
    outcome = _Outcome()
    if ready or evaluable:
        policy_source = Path(str(bank.lean_path)).read_text(encoding="utf-8")
        outcome = await _compute_ready(
            cfg, bank, policy_source, ready, binding.bound, fact_index, resolved
        )
        results.update(outcome.scores)
    ordered = [results[spec.score_id] for spec in bank.scores]
    for item in ordered:
        item.warnings = warnings.get(item.score_id, []) + ([item.caution] if item.caution else [])
    write_atomic(
        workspace_dir / "scores.json",
        json.dumps([item.model_dump(mode="json") for item in ordered], indent=2) + "\n",
    )
    add_score_inputs(resolved, bank.scores, outcome.score_values)
    evaluation = PolicyEvaluation(
        rules=build_rule_results(
            bank.rules,
            resolved,
            outcome.rule_statuses,
            outcome.artifact,
            split_policy_sections(bank.policy_md),
            fact_index,
            binding.basis.value,
        )
    )
    write_atomic(workspace_dir / "policy_eval.json", evaluation.model_dump_json(indent=2) + "\n")
    return ordered


def score_adjustments(
    ready: list[ScoreSpec], bound: dict[str, list[BoundInput]], policy_source: str
) -> dict[str, ScoreAdjustment]:
    """For each ready score, the bands that read a cautioned input and must award 0 points."""
    found = {
        spec.score_id: excluded_bands(spec, bound.get(spec.score_id, []), policy_source)
        for spec in ready
    }
    return {score_id: item for score_id, item in found.items() if item is not None}


def _with_bands(result: ScoreResult, adjustment: ScoreAdjustment | None) -> ScoreResult:
    """Mark the score caution and name each band that awarded 0 points as not evaluable."""
    if adjustment is None:
        return result
    labels = [band.label for band in adjustment.bands]
    caution = f"band(s) {', '.join(labels)} awarded 0 points, {BAND_NOT_EVALUABLE}: " + "; ".join(
        f"{label}: {adjustment.reasons[label]}" for label in labels
    )
    return result.model_copy(
        update={
            "bands": dict.fromkeys(labels, BAND_NOT_EVALUABLE),
            "caution": caution,
        }
    )


def _not_evaluable(result: ScoreResult, reason: str | None) -> ScoreResult:
    """Drop the value of a non-additive score with a cautioned input and say why."""
    if reason is None or result.status is not ScoreStatus.computed:
        return result
    return result.model_copy(
        update={"value_display": None, "grade": SCORE_NOT_EVALUABLE, "caution": reason}
    )


@dataclass
class _Outcome:
    """What the Lean passes produced: score results, rule statuses, raw values, the artifact."""

    scores: dict[str, ScoreResult] = field(default_factory=dict)
    rule_statuses: dict[str, str] = field(default_factory=dict)
    score_values: dict[str, str] = field(default_factory=dict)
    artifact: LeanArtifact | None = None


async def _compute_ready(
    cfg: RunConfig,
    bank: BankPolicy,
    policy_source: str,
    ready: list[ScoreSpec],
    bound: dict[str, list[BoundInput]],
    facts: dict[str, VerifiedFact],
    resolved: dict[str, ResolvedRule],
) -> _Outcome:
    """Sync the policy, run both Lean passes, and turn the output into scores and rule statuses."""
    artifact_id = f"scores_{cfg.run_id}"
    scores_path = runs_dir(cfg.run_id) / "Scores.lean"

    def failed(artifact: LeanArtifact | None) -> _Outcome:
        return _Outcome(
            scores={
                spec.score_id: _result(
                    spec, ScoreStatus.lean_failed, bound.get(spec.score_id, []), artifact
                )
                for spec in ready
            },
            artifact=artifact,
        )

    try:
        module = await sync_policy_module(bank.bank_id, policy_source)
    except RuntimeError as error:
        compile_result = CompileResult(ok=False, stderr=str(error))
        return failed(
            make_artifact(artifact_id, "policy", scores_path, policy_source, compile_result)
        )
    ids = [spec.score_id for spec in bank.scores]
    rules = bank.rules
    adjustments = score_adjustments(ready, bound, policy_source)
    first = build_scores_lean(
        module, bank.scores, bound, facts, None, rules, resolved, adjustments=adjustments
    )
    first_compile = await _compile_source(scores_path, first)
    if not first_compile.ok:
        return failed(make_artifact(artifact_id, "scores", scores_path, first, first_compile))
    parsed = parse_eval_output(first_compile.stdout, ids)
    rule_pins = parse_rule_statuses(first_compile.stdout, rules)
    final = build_scores_lean(
        module,
        bank.scores,
        bound,
        facts,
        _pins(parsed, ready),
        rules,
        resolved,
        rule_pins,
        adjustments,
    )
    final_compile = await _compile_source(scores_path, final)
    artifact = make_artifact(artifact_id, "scores", scores_path, final, final_compile)
    if not final_compile.ok:
        return failed(artifact)
    printed = parse_eval_output(final_compile.stdout, ids)
    results = {}
    for spec in ready:
        item = printed.get(spec.score_id)
        if item is None or item.value is None or item.grade is None:
            status, value, grade = ScoreStatus.lean_failed, None, None
        else:
            status, grade = ScoreStatus.computed, item.grade
            value = format_score_value(spec, item.value)
        results[spec.score_id] = _not_evaluable(
            _with_bands(
                _result(spec, status, bound.get(spec.score_id, []), artifact, value, grade),
                adjustments.get(spec.score_id),
            ),
            not_evaluable_reason(spec, bound.get(spec.score_id, []), policy_source),
        )
    return _Outcome(
        scores=results,
        rule_statuses=parse_rule_statuses(final_compile.stdout, rules),
        score_values={sid: item.value for sid, item in printed.items() if item.value},
        artifact=artifact,
    )
