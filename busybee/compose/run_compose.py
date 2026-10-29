"""Run the compose stage: recommendation with checked ids and verdicts, then write report.json.

Verdict checks (`verdict_check.py`) remove reasons whose stated comparison is false, log them to
`compose_rejected.json`, and re-ask compose once when the decision leaned on a removed reason.
Then the policy rule engine (`policy_floor.py`) enforces the rule-implied decision floor on the
checked recommendation, adds a `policy_rule` reason for each failing or caution rule no reason
cites, always rebuilds a reduce-or-decline headline and rebuilds one that contradicts the final
decision (recording `headline_rebuilt`),
drops the proposed limit on refer and decline, and writes the outcome to
`decision_override.json` and the report's audit block."""

from pathlib import Path

from busybee.llm import Provider
from busybee.llm.messages import Message, Role
from busybee.schema.io import write_json_atomic, write_model_atomic
from busybee.schema.report import Decision, Report
from busybee.schema.run import RunConfig

from .assemble import build_report
from .audit import build_audit_block
from .check_ids import recommend_with_checks, scrub_reasons
from .inputs import load_compose_inputs
from .policy_floor import (
    enforce_policy_floor,
    exposure_limit_note,
    headline_matches_decision,
    headline_rule,
    max_exposure_crore,
    missing_rule_reasons,
    rebuild_headline,
    unevaluated_note,
)
from .prompts import TASK, build_messages
from .ratio_definitions import annotate_ratio_definitions
from .verdict_check import check_verdicts, needs_reask, reask_note


async def run_compose(
    workspace_dir: str | Path,
    cfg: RunConfig,
    provider: Provider,
    banks_dir: str | Path,
) -> Report:
    """Compose the recommendation, assemble the report, and save report.json."""
    workspace = Path(workspace_dir)
    inputs = load_compose_inputs(workspace, cfg, banks_dir)
    messages = build_messages(inputs)
    ask = dict(
        fact_ids=inputs.fact_ids,
        score_ids=inputs.score_ids,
        inference_ids=inputs.inference_ids,
        task=TASK,
        policy_sections={section.section_id: section for section in inputs.policy_sections},
        rule_ids=inputs.rule_ids,
    )
    first = await recommend_with_checks(provider, messages, **ask)
    recommendation, rejected = await check_verdicts(provider, first, inputs)
    if needs_reask(recommendation, rejected):
        again_messages = [
            *messages,
            Message(role=Role.assistant, content=first.model_dump_json()),
            Message(role=Role.user, content=reask_note(rejected)),
        ]
        second = await recommend_with_checks(provider, again_messages, **ask)
        recommendation, more = await check_verdicts(provider, second, inputs, round_no=2)
        rejected = [*rejected, *more]
    write_json_atomic(workspace / "compose_rejected.json", [r.model_dump() for r in rejected])
    recommendation, override = enforce_policy_floor(recommendation, inputs.rule_results)
    extra = scrub_reasons(
        missing_rule_reasons(recommendation, inputs.rule_results),
        fact_ids=inputs.fact_ids,
        score_ids=inputs.score_ids,
        inference_ids=inputs.inference_ids,
        policy_sections={section.section_id: section for section in inputs.policy_sections},
        rule_ids=inputs.rule_ids,
    )
    note = unevaluated_note(inputs.rule_results)
    recommendation = recommendation.model_copy(
        update={
            "key_reasons": [*recommendation.key_reasons, *extra],
            "confidence_note": " ".join(filter(None, [recommendation.confidence_note, note]))
            or None,
        }
    )
    rebuilt = (
        recommendation.decision is Decision.reduce_or_decline
        or not headline_matches_decision(recommendation.headline, recommendation.decision)
    )
    chosen = headline_rule(recommendation.decision, inputs.rule_results)
    if rebuilt:
        headline = rebuild_headline(
            recommendation.decision,
            inputs.rule_results,
            recommendation.headline,
            recommendation.proposed_limit,
            max_exposure_crore(inputs.scores),
            exposure_limit_note(inputs.scores),
        )
        recommendation = recommendation.model_copy(update={"headline": headline})
        override = override.model_copy(update={"headline": headline})
    if recommendation.decision in (
        Decision.refer,
        Decision.decline,
        Decision.reduce_or_decline,
    ):
        recommendation = recommendation.model_copy(update={"proposed_limit": None})
    write_json_atomic(
        workspace / "decision_override.json",
        {
            **override.model_dump(mode="json"),
            "headline_rebuilt": rebuilt,
            "headline_rule_id": chosen.rule_id if rebuilt and chosen else None,
        },
    )
    inputs, recommendation = annotate_ratio_definitions(inputs, recommendation)
    audit = build_audit_block(
        workspace,
        inputs.policy,
        stage_models=cfg.models,
    )
    audit.decision_override = override if override.overridden else None
    report = build_report(cfg, inputs, recommendation, audit)
    write_model_atomic(workspace / "report.json", report)
    return report
