"""Build citable statement fragments, citation chips, the Lean popover records, and band badges."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any

from markupsafe import Markup, escape

from busybee.render import score_figures
from busybee.render.fact_fields import fact_field
from busybee.render.links import lean_href
from busybee.schema.facts import (
    Citation,
    ConflictNote,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.lean import LeanArtifact
from busybee.schema.policy import (
    BoundInput,
    GradeRule,
    InputSlot,
    RuleResult,
    RuleStatus,
    ScoreResult,
    ScoreStatus,
)
from busybee.schema.report import Concern, Inference, KeyReason, PolicyCitation

_CATEGORY_LABELS = {
    "debt_leverage": "Debt and leverage",
    "cash_flow": "Cash flow",
    "credit_history": "Credit history",
    "ownership_governance": "Ownership and governance",
    "litigation_regulatory": "Litigation and regulatory",
    "industry_market": "Industry and market",
}

_GRADE_TONES = {
    "strong": "good",
    "comfortable": "good",
    "low risk": "good",
    "within limit": "good",
    "satisfactory": "good",
    "adequate": "fair",
    "acceptable risk": "fair",
    "moderate": "weak",
    "high risk": "weak",
    "watch": "weak",
    "weak": "poor",
    "decline": "poor",
    "breach": "poor",
    "exceeds limit": "poor",
}

_CONFIDENCE_LABELS = {
    "high": "High confidence",
    "medium": "Medium confidence",
    "low": "Low confidence",
}


def humanise(value: str) -> str:
    """Turn a snake_case or camelCase identifier into spaced, sentence-case words."""
    words = [word for word in str(value).replace("_", " ").replace("-", " ").split() if word]
    if not words:
        return ""
    first = words[0] if words[0].isupper() else words[0][:1].upper() + words[0][1:]
    rest = [word if word.isupper() else word.lower() for word in words[1:]]
    return " ".join([first, *rest])


def humanise_category(category: object) -> str:
    """Return the human label for a FactCategory or category string."""
    key = getattr(category, "value", str(category))
    return _CATEGORY_LABELS.get(key, humanise(key))


def citation_chip_html(
    citations: Sequence[Citation],
    verification: Verification | None = None,
    *,
    element_id: str | None = None,
) -> Markup:
    """Return the citation chip for a statement, or an empty Markup without citations."""
    if not citations:
        return Markup("")
    first = citations[0]
    chunk_ids = ",".join(citation.chunk_id for citation in citations)
    status = verification.status.value if verification else "supported"
    method = verification.method if verification else ""
    attributes = [
        'class="bb-cite"',
        'type="button"',
        f'data-cites="{escape(chunk_ids)}"',
        f'data-quotes="{escape(json.dumps([citation.quote for citation in citations]))}"',
        f'data-status="{escape(status)}"',
    ]
    if method:
        attributes.append(f'data-method="{escape(method)}"')
    if element_id:
        attributes.append(f'id="{escape(element_id)}-cite"')
    more = (
        Markup(f'<span class="bb-cite-more">+{len(citations) - 1}</span>')
        if len(citations) > 1
        else Markup("")
    )
    if first.source == "bank_input":
        attributes[0] = 'class="bb-cite bb-cite--bank"'
        label = "bank input"
    else:
        label = f'{escape(first.doc_id)}<span class="bb-cite-sep">·</span>p.{escape(first.page_no)}'
    return Markup(f"<button {' '.join(attributes)}>{label}{more}</button>")


def statement_html(
    text: str,
    citations: Sequence[Citation],
    element_id: str,
    verification: Verification | None = None,
) -> Markup:
    """Return an escaped statement followed immediately by its citation chip."""
    chip = citation_chip_html(citations, verification, element_id=element_id)
    return Markup(f"{escape(text)}{chip}")


def id_tag_html(statement_id: str) -> Markup:
    """Return the muted monospace id that closes a statement, linking to its anchor."""
    return Markup(
        f'<a class="bb-sid" href="#{escape(_anchor_for(statement_id))}">{escape(statement_id)}</a>'
    )


def _anchor_for(statement_id: str) -> str:
    """Return the element id of the statement a bare F/I/C id names."""
    prefix = {"F": "fact-", "I": "inf-", "C": "concern-"}.get(statement_id[:1], "")
    return f"{prefix}{statement_id}"


def statement_with_id_html(
    text: str,
    statement_id: str,
    citations: Sequence[Citation],
    verification: Verification | None = None,
) -> Markup:
    """Return statement text, then its trailing id, then its citation chip."""
    chip = citation_chip_html(citations, verification, element_id=_anchor_for(statement_id))
    return Markup(f"{escape(text)} {id_tag_html(statement_id)}{chip}")


def conflicted_fact(fact: VerifiedFact) -> bool:
    """True for a fact that lost a cross-document conflict (appendix only)."""
    return (
        fact.verification is not None and fact.verification.status is VerificationStatus.conflicted
    )


def conflict_badge_html(conflicts: Sequence[ConflictNote]) -> Markup:
    """Return the small "conflict" badge whose popover lists the other fact ids and notes."""
    if not conflicts:
        return Markup("")
    items = "".join(
        f'<li><span class="bb-mono">{escape(item.fact_id)}</span> {escape(item.note)}</li>'
        for item in conflicts
    )
    return Markup(
        ' <span class="bb-badge bb-conflict" data-status="conflict" tabindex="0">conflict'
        f'<span class="bb-conflict-pop" role="tooltip"><ul>{items}</ul></span></span>'
    )


def lean_chip_html(record_id: str, status: str) -> Markup:
    """Return the Lean chip that opens a score or inference popover."""
    return Markup(
        '<button class="bb-cite bb-cite--lean" type="button" '
        f'data-lean="{escape(record_id)}" data-status="{escape(status)}">Lean</button>'
    )


def lean_status_for_score(score: ScoreResult) -> str:
    """Map a ScoreResult to proved, failed, or unchecked."""
    if score.status is ScoreStatus.not_computable:
        return "unchecked"
    if score.status is ScoreStatus.lean_failed:
        return "failed"
    if score.lean is not None and score.lean.compile is not None and score.lean.compile.ok:
        return "proved"
    return "unchecked"


def lean_status_for_inference(inference: Inference) -> str | None:
    """Return the Lean chip status for an inference, or None when it is a judgement."""
    if not inference.quantitative:
        return None
    if inference.lean is None or inference.lean.compile is None:
        return "unchecked"
    return "proved" if inference.lean.compile.ok else "failed"


def tone_for_index(index: int, count: int) -> str:
    """Map a grade's position in a best-to-worst list to a badge tone."""
    if count <= 0:
        return "none"
    if count == 1:
        return "good"
    if count == 2:
        return ("good", "poor")[index]
    if count == 3:
        return ("good", "weak", "poor")[index]
    if count == 4:
        return ("good", "fair", "weak", "poor")[index]
    palette = ("good", "fair", "weak", "poor")
    position = round(index * (len(palette) - 1) / (count - 1))
    return palette[position]


def _grade_labels(grades: Iterable[GradeRule | str] | None) -> list[str]:
    """Return grade labels from GradeRule models or plain strings."""
    if not grades:
        return []
    return [grade.label if isinstance(grade, GradeRule) else str(grade) for grade in grades]


def grade_tone(grade: str | None, grades: Iterable[GradeRule | str] | None = None) -> str:
    """Return the badge tone for a grade, using the spec order when available."""
    if not grade:
        return "none"
    labels = _grade_labels(grades)
    if grade in labels:
        return tone_for_index(labels.index(grade), len(labels))
    return _GRADE_TONES.get(grade.strip().lower(), "none")


def _fact_links(fact_ids: Sequence[str]) -> Markup:
    """Return fact-id links that keep the back stack."""
    return Markup(
        "".join(
            f'<a class="bb-ref bb-jump" href="#fact-{escape(fact_id)}">{escape(fact_id)}</a>'
            for fact_id in fact_ids
        )
    )


def _confidence(confidence: float) -> tuple[str, str]:
    """Return the level and label for a 0-1 (or 0-100) confidence value."""
    value = confidence / 100 if confidence > 1 else confidence
    if value >= 0.7:
        level = "high"
    elif value >= 0.4:
        level = "medium"
    else:
        level = "low"
    return level, _CONFIDENCE_LABELS[level]


def policy_chip_html(citations: Sequence[PolicyCitation]) -> Markup:
    """Return the chip that opens the cited policy clauses, or nothing without citations."""
    if not citations:
        return Markup("")
    more = (
        Markup(f'<span class="bb-cite-more">+{len(citations) - 1}</span>')
        if len(citations) > 1
        else Markup("")
    )
    ids = ",".join(citation.section_id for citation in citations)
    return Markup(
        '<button class="bb-cite" type="button" '
        f'data-cites="{escape(ids)}" data-status="supported" data-method="policy">'
        f'Policy<span class="bb-cite-sep">·</span>{escape(citations[0].section_id)}{more}'
        "</button>"
    )


def key_reason_html(reason: KeyReason, number: int) -> Markup:
    """Return one recommendation reason as a citable statement with evidence refs."""
    links: list[str] = []
    links.extend(
        f'<a class="bb-ref bb-jump" href="#fact-{escape(fact_id)}">{escape(fact_id)}</a>'
        for fact_id in reason.fact_ids
    )
    links.extend(
        f'<a class="bb-ref bb-jump" href="#score-{escape(score_id)}">{escape(score_id)}</a>'
        for score_id in reason.score_ids
    )
    links.extend(
        f'<a class="bb-ref bb-jump" href="#inf-{escape(inference_id)}">{escape(inference_id)}</a>'
        for inference_id in reason.inference_ids
    )
    links.extend(
        f'<a class="bb-ref bb-jump" href="#rule-{escape(rule_id)}">{escape(rule_id)}</a>'
        for rule_id in reason.rule_ids
    )
    reference_html = Markup(f" {Markup(' '.join(links))}") if links else Markup("")
    return Markup(
        f'<li class="bb-stmt" id="rec-r{number}" data-ref="Reason {number}">'
        f"{escape(reason.text)}{policy_chip_html(reason.policy_citations)}{reference_html}</li>"
    )


def score_statement_html(
    score: ScoreResult,
    *,
    name: str | None = None,
    grades: Iterable[GradeRule | str] | None = None,
    siblings: Sequence[ScoreResult] = (),
) -> Markup:
    """Return one score line: label, leader, value, grade and Lean chip, then a notes row."""
    score_id = escape(score.score_id)
    display_name = escape(name or humanise(score.score_id))
    computed = score.status is ScoreStatus.computed and bool(score.value_display)
    value = escape(score.value_display) if computed else Markup("not computable")
    proposed = score_figures.proposed_exposure_text(score) if computed else None
    if proposed:
        value = Markup(f'{escape(proposed)} <span class="bb-score-note bb-muted">bank input</span>')
    limit_note = score_figures.policy_limit_note(score, siblings) if proposed else None
    value_class = "bb-score-value" if computed else "bb-score-value bb-score-value--none"
    grade = score.grade or (
        f"Missing {len(score.unbound)} input{'s' if len(score.unbound) != 1 else ''}"
        if score.unbound
        else "No grade"
    )
    why = "; ".join(f"{slot}: {reason}" for slot, reason in score.unbound.items())
    why_attr = f' title="{escape(why)}"' if why else ""
    tone = grade_tone(score.grade, grades)
    chip = lean_chip_html(score.score_id, lean_status_for_score(score))
    warn = (
        '<span class="bb-badge" data-status="unchecked" '
        f'title="{escape("; ".join(score.warnings))}">'
        f"{len(score.warnings)} warning{'s' if len(score.warnings) != 1 else ''}</span>"
        if score.warnings
        else ""
    )
    bands = "".join(
        f'<span class="bb-badge" data-status="caution" title="{escape(score.caution)}">'
        f"{escape(score_figures.band_figure_text(score, band, state) or band_text(band, state))}"
        "</span>"
        for band, state in score.bands.items()
    )
    limit = (
        f'<span class="bb-score-note bb-muted">{escape(limit_note)}</span>' if limit_note else ""
    )
    notes = (
        f'<span class="bb-score-notes">{limit}{bands}{warn}</span>'
        if limit or bands or warn
        else ""
    )
    return Markup(
        f'<li class="bb-score bb-stmt" id="score-{score_id}" data-ref="{score_id}"{why_attr}>'
        f'<span class="bb-score-name">{display_name}</span>'
        '<span class="bb-score-leader" aria-hidden="true"></span>'
        f'<span class="{value_class}">{value}</span>'
        f'<span class="bb-badge bb-grade" data-tone="{tone}">{escape(grade)}</span>'
        f"{chip}{notes}</li>"
    )


def band_text(band: str, state: str) -> str:
    """How the report names a band that awarded no points, e.g. 'DSCR band: not evaluable'."""
    name = band.upper() if len(band) <= 4 else band.replace("_", " ").capitalize()
    return f"{name} band: {state}"


_RULE_LABELS = {
    RuleStatus.passed: ("Pass", "good"),
    RuleStatus.caution: ("Caution", "weak"),
    RuleStatus.fail: ("Fail", "poor"),
    RuleStatus.not_evaluable: ("Not evaluable", "none"),
}


def rule_lean_key(rule: RuleResult) -> str:
    """The #bb-lean key of a rule, kept apart from score and inference ids."""
    return f"rule:{rule.rule_id}"


def lean_status_for_rule(rule: RuleResult) -> str:
    """Map a RuleResult to proved, failed, or unchecked."""
    if rule.lean is None or rule.lean.compile is None:
        return "unchecked"
    if rule.status is RuleStatus.not_evaluable:
        return "failed" if not rule.lean.compile.ok else "unchecked"
    return "proved" if rule.lean.compile.ok else "failed"


_ACRONYMS = {"ebitda", "cfads", "dscr", "icr", "tnw", "ltv", "roe", "roce", "emi", "gst", "pat"}


def slot_label(slot: str) -> str:
    """Return the human label of an input slot (acronyms upper-cased)."""
    words = [word for word in str(slot).replace("_", " ").split() if word]
    return " ".join(
        word.upper() if word.lower() in _ACRONYMS else (word if i else word[:1].upper() + word[1:])
        for i, word in enumerate(words)
    )


def slot_index(score_specs: Mapping[str, Any] | None) -> dict[str, InputSlot]:
    """Map every slot name to its InputSlot across the bank's score specs."""
    slots: dict[str, InputSlot] = {}
    for spec in (score_specs or {}).values():
        for slot in spec.inputs:
            slots.setdefault(slot.slot, slot)
    return slots


def format_value(item: BoundInput, slots: Mapping[str, InputSlot] | None = None) -> str:
    """Return the value in the slot's display unit: "141.82 crore", "1.25x", "12.50%", "3"."""
    spec = (slots or {}).get(item.slot)
    if spec is None:
        return f"{item.value:f}" + (f" {item.unit}" if item.unit else "")
    unit = (spec.unit or item.unit).lower()
    value = Decimal(item.value_scaled) / Decimal(spec.scale or 1)
    if "crore" in unit:
        return f"{value:.2f} crore"
    if "lakh" in unit:
        return f"{value:.2f} lakh"
    if unit in {"x", "ratio", "times"}:
        return f"{value:.2f}x"
    if unit in {"%", "percent", "pct", "percentage"}:
        return f"{value:.2f}%"
    plain = f"{value:f}"
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain


def format_input(item: BoundInput, slots: Mapping[str, InputSlot] | None = None) -> str:
    """Return "EBITDA 141.82 crore": the slot label and its value in the display unit."""
    return f"{slot_label(item.slot)} {format_value(item, slots)}"


def _rule_inputs_html(rule: RuleResult, slots: Mapping[str, InputSlot] | None = None) -> Markup:
    if rule.status is RuleStatus.not_evaluable and rule.unbound:
        text = "; ".join(f"{slot}: {reason}" for slot, reason in rule.unbound.items())
        return Markup(f'<span class="bb-small bb-muted">Missing {escape(text)}</span>')
    parts = []
    for item in rule.inputs:
        value = format_input(item, slots)
        fact_id = escape(item.fact_id)
        link = (
            f' <a class="bb-ref bb-jump" href="#fact-{fact_id}">{fact_id}</a>'
            if item.fact_id
            else f' <a class="bb-ref bb-jump" href="#score-{escape(item.slot)}">score</a>'
        )
        parts.append(
            f'<span class="bb-rule-input" data-slot="{escape(item.slot)}">'
            f"{escape(value)}{link}</span>"
        )
    return Markup("<br>".join(parts))


def rule_row_html(rule: RuleResult, slots: Mapping[str, InputSlot] | None = None) -> Markup:
    """Return one row of the policy rule table: name, inputs, result badge and Lean chip."""
    label, tone = _RULE_LABELS[rule.status]
    rule_id = escape(rule.rule_id)
    section = (
        f' <a class="bb-ref" href="policy.html#{escape(rule.policy_section_id)}">'
        f"Policy §{escape(rule.policy_section)}</a>"
        if rule.policy_section_id
        else ""
    )
    message = (
        f'<span class="bb-small bb-muted bb-rule-message">{escape(rule.message)}{section}</span>'
        if rule.message
        else ""
    )
    chip = lean_chip_html(rule_lean_key(rule), lean_status_for_rule(rule))
    return Markup(
        f'<tr class="bb-rule bb-stmt" id="rule-{rule_id}" data-ref="{rule_id}" '
        f'data-status="{escape(rule.status.value)}">'
        f'<th scope="row">{escape(rule.name)}<br>{message}</th>'
        f"<td>{_rule_inputs_html(rule, slots)}</td>"
        f'<td><span class="bb-badge bb-grade" data-tone="{tone}">{label}</span></td>'
        f"<td>{chip}</td></tr>"
    )


def rule_lean_record(
    rule: RuleResult,
    facts: Mapping[str, VerifiedFact],
    slots: Mapping[str, InputSlot] | None = None,
) -> dict[str, Any]:
    """Return the #bb-lean payload for one policy rule."""
    artifact = rule.lean
    label, tone = _RULE_LABELS[rule.status]
    theorems = [
        name for name in (artifact.theorems if artifact else []) if f"rule_{rule.rule_id}" in name
    ]
    return {
        "kind": "rule",
        "title": rule.name,
        "status": lean_status_for_rule(rule),
        "grade": label,
        "grade_tone": tone,
        "claim": rule.expression,
        "warnings": [f"{slot}: {reason}" for slot, reason in rule.unbound.items()],
        "theorems": theorems,
        "bindings": [_binding_record(binding, facts, slots) for binding in rule.inputs],
        "compile": _compile_record(artifact),
        "href": lean_href(artifact.artifact_id) if artifact else None,
    }


def inference_html(inference: Inference) -> Markup:
    """Return one inference block, marking whether Lean proved it."""
    status = lean_status_for_inference(inference)
    chip = lean_chip_html(inference.inference_id, status) if status else Markup("")
    if not inference.quantitative:
        badge = '<span class="bb-badge" data-status="unchecked">Judgement</span>'
    elif status == "proved":
        badge = '<span class="bb-badge" data-status="proved">Proved in Lean</span>'
    elif status == "failed":
        badge = '<span class="bb-badge" data-status="failed">Lean failed</span>'
    else:
        badge = '<span class="bb-badge" data-status="unchecked">Lean unchecked</span>'
    level, label = _confidence(inference.confidence)
    facts = _fact_links(inference.fact_ids)
    facts_block = (
        f'<p class="bb-block-facts"><span class="bb-caps">Facts</span>{facts}</p>'
        if inference.fact_ids
        else ""
    )
    reasoning_block = (
        f'<p class="bb-reasoning">{escape(inference.reasoning)}</p>' if inference.reasoning else ""
    )
    return Markup(
        f'<article class="bb-block bb-inference bb-stmt" '
        f'id="inf-{escape(inference.inference_id)}" data-ref="{escape(inference.inference_id)}">'
        f'<p class="bb-opinion">{escape(inference.opinion)} '
        f"{id_tag_html(inference.inference_id)}{chip}</p>"
        f"{facts_block}{reasoning_block}"
        '<div class="bb-block-meta">'
        f'<span class="bb-badge bb-confidence" data-level="{level}">{label}</span>'
        f"{badge}</div></article>"
    )


def concern_html(concern: Concern) -> Markup:
    """Return one open-concern block with the vDB query that was searched."""
    status = "supported" if concern.found else "unsupported"
    label = "Addressed in documents" if concern.found else "Not found in documents"
    if concern.concern_id.startswith("CF"):
        status, label = "conflict", "Sources conflict"
    facts = _fact_links(concern.fact_ids)
    facts_block = (
        f'<p class="bb-block-facts"><span class="bb-caps">Facts</span>{facts}</p>'
        if concern.fact_ids
        else ""
    )
    reasoning_block = (
        f'<p class="bb-reasoning">{escape(concern.reasoning)}</p>' if concern.reasoning else ""
    )
    query_block = (
        '<p class="bb-query"><span class="bb-caps">Searched</span>'
        f"<q>{escape(concern.query_used)}</q></p>"
        if concern.query_used
        else ""
    )
    return Markup(
        f'<article class="bb-block bb-concern bb-stmt" '
        f'id="concern-{escape(concern.concern_id)}" data-ref="{escape(concern.concern_id)}">'
        f'<p class="bb-opinion">{escape(concern.opinion)} '
        f"{id_tag_html(concern.concern_id)}</p>"
        f"{facts_block}{reasoning_block}{query_block}"
        f'<div class="bb-block-meta"><span class="bb-badge" data-status="{status}">{label}</span>'
        "</div></article>"
    )


def _compile_record(artifact: LeanArtifact | None) -> dict[str, Any] | None:
    """Return the popover's compile record, or None when nothing was compiled."""
    if artifact is None or artifact.compile is None:
        return None
    result = artifact.compile
    return {
        "ok": result.ok,
        "duration_s": result.duration_s,
        "toolchain": result.toolchain,
        "output": (result.stdout or "") + (result.stderr or ""),
    }


def _binding_record(
    binding: BoundInput,
    facts: Mapping[str, VerifiedFact],
    slots: Mapping[str, InputSlot] | None = None,
) -> dict[str, Any]:
    """Return one fact-to-Lean binding, including the source chunk of the fact."""
    fact = facts.get(binding.fact_id) if binding.fact_id else None
    chunk_id = fact.citations[0].chunk_id if fact and fact.citations else None
    record: dict[str, Any] = {
        "slot": binding.slot,
        "fact_id": binding.fact_id or None,
        "value": str(binding.value) if binding.value is not None else None,
        "unit": binding.unit,
        "value_scaled": binding.value_scaled,
        "chunk_id": chunk_id,
        "display": format_value(binding, slots),
    }
    fact_record = fact_field(fact, "record") if fact is not None else None
    if fact_record is not None:
        record["metric"] = fact_record.metric
    if binding.derived_from:
        record["derived_from"] = list(binding.derived_from)
    if binding.fact_id:
        record["fact_href"] = f"#fact-{binding.fact_id}"
    if binding.note:
        record["note"] = binding.note
    elif not binding.fact_id:
        record["note"] = "unbound"
    return record


def score_lean_record(
    score: ScoreResult,
    facts: Mapping[str, VerifiedFact],
    *,
    name: str | None = None,
    grades: Iterable[GradeRule | str] | None = None,
    slots: Mapping[str, InputSlot] | None = None,
) -> dict[str, Any]:
    """Return the #bb-lean payload for one score."""
    artifact = score.lean
    return {
        "kind": "score",
        "title": name or humanise(score.score_id),
        "status": lean_status_for_score(score),
        "value_display": score.value_display,
        "grade": score.grade,
        "grade_tone": grade_tone(score.grade, grades),
        "claim": artifact.theorems[0] if artifact and artifact.theorems else None,
        "warnings": list(score.warnings),
        "caution": score.caution,
        "bands": {band: band_text(band, state) for band, state in score.bands.items()},
        "bindings": [_binding_record(binding, facts, slots) for binding in score.inputs],
        "compile": _compile_record(artifact),
        "href": lean_href(artifact.artifact_id) if artifact else None,
    }


def inference_lean_record(
    inference: Inference, facts: Mapping[str, VerifiedFact]
) -> dict[str, Any]:
    """Return the #bb-lean payload for a quantitative inference."""
    artifact = inference.lean
    return {
        "kind": "inference",
        "title": inference.opinion or f"Inference {inference.inference_id}",
        "status": lean_status_for_inference(inference) or "unchecked",
        "claim": artifact.theorems[0] if artifact and artifact.theorems else None,
        "bindings": [],
        "compile": _compile_record(artifact),
        "href": lean_href(artifact.artifact_id) if artifact else None,
    }
