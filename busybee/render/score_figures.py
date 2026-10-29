"""Figures shown beside a policy score line: band ratios with their points, and zero-limit notes.

A score the policy builds from bands (`leverage_points net_debt ebitda`) lists in its generated
Lean source one call per excluded band, with the score's own slot names as arguments. For a
band with two arguments the report shows the ratio of their normalised input values (all money
is already scaled to one unit, so the ratio is unit-free) next to the points the band awarded,
e.g. "Leverage 7.50x · 0 pts (proxy input)". `limit_zero_note` explains a limit score that is
0 because the policy permits no exposure at the grade another score produced, by finding which
sibling score the limit's Lean value line takes as an argument. A limit score (one that binds a
proposed exposure, turnover and net worth) is shown as the bank's proposed exposure with the
policy limit and its caps described in a note; the turnover cap uses the smaller of the projected
turnover and 125 percent of the latest audited turnover. Every function returns None
when the data to compute a figure is not in the score, so callers fall back to the plain text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from busybee.schema.policy import ScoreResult

_BAND_CALL = re.compile(r"\(\s*[\w.]*?(\w+)_points\s+([\w\s]+?)\)")
_MONEY_WORD = re.compile(r"^(-?[\d,]+(?:\.\d+)?) crore$")
_LIMIT_SLOTS = ("proposed_exposure", "projected_turnover", "tangible_net_worth")


def _band_name(label: str) -> str:
    """Name a band for the report: short names upper-cased, longer ones sentence-cased."""
    return label.upper() if len(label) <= 4 else label.replace("_", " ").capitalize()


def _band_arguments(score: ScoreResult, label: str) -> list[str]:
    """Slot names the band called `label` reads, taken from the score's Lean source."""
    source = score.lean.source if score.lean else ""
    for function, arguments in _BAND_CALL.findall(source):
        if function == label:
            prefix = f"{score.score_id}_"
            return [word.removeprefix(prefix) for word in arguments.split()]
    return []


def band_ratio(score: ScoreResult, label: str) -> float | None:
    """The first-over-second ratio of a two-argument band's input values, or None."""
    names = _band_arguments(score, label)
    scaled = {item.slot: item.value_scaled for item in score.inputs}
    if len(names) != 2 or not all(name in scaled for name in names):
        return None
    numerator, denominator = scaled[names[0]], scaled[names[1]]
    return numerator / denominator if denominator > 0 else None


def band_figure_text(score: ScoreResult, label: str, state: str) -> str | None:
    """Return e.g. 'Leverage 7.50x · 0 pts (proxy input)', or None when no ratio is available."""
    ratio = band_ratio(score, label)
    if ratio is None:
        return None
    reason = "proxy input" if "proxy" in state else state
    return f"{_band_name(label)} {ratio:.2f}x · 0 pts ({reason})"


def _crore(scaled: int) -> str:
    """Format a crore x 100 integer as 'INR 12.5 crore'."""
    return "INR " + f"{scaled / 100:.2f}".rstrip("0").rstrip(".") + " crore"


def _scaled_inputs(score: ScoreResult) -> dict[str, int]:
    return {item.slot: item.value_scaled for item in score.inputs}


def proposed_exposure_text(score: ScoreResult) -> str | None:
    """'INR 150 crore' for a limit score that carries the bank's proposed exposure, else None."""
    scaled = _scaled_inputs(score)
    if not all(slot in scaled for slot in _LIMIT_SLOTS) or not score.value_display:
        return None
    return _crore(scaled["proposed_exposure"])


def _grade_of_limit(score: ScoreResult, scores: Sequence[ScoreResult]) -> ScoreResult | None:
    """The sibling score whose value the limit's Lean value line takes as an argument."""
    for line in (score.lean.source if score.lean else "").splitlines():
        if line.startswith(f"def {score.score_id}_value"):
            for sibling in scores:
                if sibling.score_id != score.score_id and f" {sibling.score_id}_value" in line:
                    return sibling
    return None


def _capped_turnover_x4(scaled: dict[str, int]) -> int:
    """4 x the smaller of projected turnover and 125% of audited turnover (policy section 7)."""
    projected = 4 * scaled["projected_turnover"]
    audited = scaled.get("revenue_current")
    return projected if audited is None else min(projected, 5 * audited)


def _percentage_of(limit: int, turnover_x4: int, net_worth: int) -> int | None:
    """The exposure percentage P whose two caps give `limit`, or None when none matches."""
    for percentage in range(101):
        if min(percentage * turnover_x4 // 2000, percentage * net_worth // 100) == limit:
            return percentage
    return None


def policy_limit_note(score: ScoreResult, scores: Sequence[ScoreResult]) -> str | None:
    """'Policy limit INR X crore (why)' for a limit score, or None when it is not one."""
    scaled = _scaled_inputs(score)
    match = _MONEY_WORD.match(score.value_display or "")
    if proposed_exposure_text(score) is None or match is None:
        return None
    limit = round(float(match.group(1).replace(",", "")) * 100)
    head = f"Policy limit {_crore(limit)}"
    if limit == 0:
        sibling = _grade_of_limit(score, scores)
        grade = sibling.value_display if sibling else None
        return f"{head} (no exposure permitted at grade {grade})" if grade else head
    turnover_x4 = _capped_turnover_x4(scaled)
    percentage = _percentage_of(limit, turnover_x4, scaled["tangible_net_worth"])
    if percentage is None or percentage == 0:
        return head
    turnover_cap = percentage * turnover_x4 // 2000
    worth_cap = percentage * scaled["tangible_net_worth"] // 100
    return (
        f"{head} (lower of turnover cap {_crore(turnover_cap)} and "
        f"net-worth cap {_crore(worth_cap)} at {percentage}%)"
    )
