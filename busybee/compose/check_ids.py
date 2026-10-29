"""Scrub recommendation evidence ids, enforce usable reasons, and re-ask once."""

from collections.abc import Mapping, Sequence

from busybee.llm import Provider, complete_as
from busybee.llm.messages import Message, Role
from busybee.policy.policy_sections import PolicySection
from busybee.schema.report import KeyReason, PolicyCitation, Recommendation

from .prompts import RecommendationOutput

MIN_KEY_REASONS = 2
FALLBACK_QUOTE_CHARS = 300


def _unique_known(ids: Sequence[str], known: set[str]) -> list[str]:
    """Return known ids once each, preserving their original order."""
    seen: set[str] = set()
    kept: list[str] = []
    for item in ids:
        if item in known and item not in seen:
            kept.append(item)
            seen.add(item)
    return kept


def _squash(text: str) -> str:
    """Collapse whitespace and lower-case text for tolerant quote matching."""
    return " ".join(text.split()).lower()


def _fallback_quote(section: PolicySection) -> str:
    """Return the opening of a section's text, cut at a word boundary."""
    text = " ".join(section.text.split())
    if len(text) <= FALLBACK_QUOTE_CHARS:
        return text
    return text[:FALLBACK_QUOTE_CHARS].rsplit(" ", 1)[0] + " ..."


def _checked_citations(
    citations: Sequence[PolicyCitation], sections: Mapping[str, PolicySection]
) -> list[PolicyCitation]:
    """Keep one citation per known section, fixing its heading and any non-verbatim quote."""
    kept: dict[str, PolicyCitation] = {}
    for citation in citations:
        section = sections.get(citation.section_id)
        if section is None or section.section_id in kept:
            continue
        quote = citation.quote.strip()
        if not quote or _squash(quote) not in _squash(section.text):
            quote = _fallback_quote(section)
        kept[section.section_id] = PolicyCitation(
            section_id=section.section_id, heading=section.heading, quote=quote
        )
    return list(kept.values())


def scrub_reasons(
    reasons: Sequence[KeyReason],
    *,
    fact_ids: set[str],
    score_ids: set[str],
    inference_ids: set[str],
    policy_sections: Mapping[str, PolicySection] | None = None,
    rule_ids: set[str] | None = None,
) -> list[KeyReason]:
    """Drop unknown ids, downgrade unsupported policy rules, and drop uncited reasons.

    A reason that cites an evaluated policy rule id is a `policy_rule` reason.
    """
    sections = policy_sections or {}
    cleaned: list[KeyReason] = []
    for reason in reasons:
        citations = _checked_citations(reason.policy_citations, sections)
        rules = _unique_known(reason.rule_ids, rule_ids or set())
        kind = (
            "policy_rule"
            if rules
            else reason.kind
            if reason.kind != "policy_rule" or citations
            else "hard_fact"
        )
        kept = KeyReason(
            text=reason.text,
            kind=kind,
            policy_citations=citations,
            fact_ids=_unique_known(reason.fact_ids, fact_ids),
            score_ids=_unique_known(reason.score_ids, score_ids),
            inference_ids=_unique_known(reason.inference_ids, inference_ids),
            rule_ids=rules,
        )
        if (
            kept.fact_ids
            or kept.score_ids
            or kept.inference_ids
            or kept.policy_citations
            or kept.rule_ids
        ):
            cleaned.append(kept)
    return cleaned


def reason_problems(reasons: Sequence[KeyReason]) -> list[str]:
    """Return the problems that require the model to try the recommendation again."""
    if len(reasons) >= MIN_KEY_REASONS:
        return []
    return [
        f"Only {len(reasons)} key reason(s) survived id checking; at least "
        f"{MIN_KEY_REASONS} reasons with existing evidence ids are required."
    ]


def recommendation_from_output(
    output: RecommendationOutput,
    *,
    fact_ids: set[str],
    score_ids: set[str],
    inference_ids: set[str],
    policy_sections: Mapping[str, PolicySection] | None = None,
    rule_ids: set[str] | None = None,
) -> tuple[Recommendation, list[str]]:
    """Build a Recommendation with only existing evidence and report any problems."""
    reasons = scrub_reasons(
        output.key_reasons,
        fact_ids=fact_ids,
        score_ids=score_ids,
        inference_ids=inference_ids,
        policy_sections=policy_sections,
        rule_ids=rule_ids,
    )
    recommendation = Recommendation(
        decision=output.decision,
        headline=output.headline,
        proposed_limit=output.proposed_limit,
        conditions=output.conditions,
        key_reasons=reasons,
        confidence_note=output.confidence_note or None,
    )
    return recommendation, reason_problems(reasons)


def reask_instruction(
    problems: Sequence[str],
    *,
    fact_ids: set[str],
    score_ids: set[str],
    inference_ids: set[str],
    policy_section_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> str:
    """Return the follow-up message that tells the model what to fix."""
    return (
        "Your previous recommendation failed evidence checking: "
        f"{' '.join(problems)} Return the whole recommendation again as JSON. "
        "Use only these ids: "
        f"facts={sorted(fact_ids)}, scores={sorted(score_ids)}, "
        f"inferences={sorted(inference_ids)}, "
        f"policy rules={sorted(rule_ids or set())}, "
        f"policy sections={sorted(policy_section_ids or set())}. "
        f"Give between {MIN_KEY_REASONS} and 6 key reasons, each citing at least one id; "
        "a policy_rule reason needs a valid policy section id."
    )


async def recommend_with_checks(
    provider: Provider,
    messages: list[Message],
    *,
    fact_ids: set[str],
    score_ids: set[str],
    inference_ids: set[str],
    task: str,
    policy_sections: Mapping[str, PolicySection] | None = None,
    rule_ids: set[str] | None = None,
) -> Recommendation:
    """Ask for a recommendation, scrub ids, and re-ask once when too few reasons remain."""
    output = await complete_as(provider, messages, RecommendationOutput, task=task)
    recommendation, problems = recommendation_from_output(
        output,
        fact_ids=fact_ids,
        score_ids=score_ids,
        inference_ids=inference_ids,
        policy_sections=policy_sections,
        rule_ids=rule_ids,
    )
    if not problems:
        return recommendation
    retry_messages = [
        *messages,
        Message(role=Role.assistant, content=output.model_dump_json()),
        Message(
            role=Role.user,
            content=reask_instruction(
                problems,
                fact_ids=fact_ids,
                score_ids=score_ids,
                inference_ids=inference_ids,
                policy_section_ids=set(policy_sections or {}),
                rule_ids=rule_ids,
            ),
        ),
    ]
    output = await complete_as(provider, retry_messages, RecommendationOutput, task=task)
    recommendation, _ = recommendation_from_output(
        output,
        fact_ids=fact_ids,
        score_ids=score_ids,
        inference_ids=inference_ids,
        policy_sections=policy_sections,
        rule_ids=rule_ids,
    )
    return recommendation
