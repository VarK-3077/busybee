"""Scoring bands that must not award points because an input is a proxy or misses components.

A points score such as the Financial Strength Score is, in the bank's `policy.lean`, a sum of
band functions applied to the score's own parameters (`leverage_points net_debt ebitda + ...`).
`score_bands` reads that sum from the policy source: every `+`-separated term of the score
function's body that is a function call whose arguments are all parameters is a band.
`excluded_bands` names the bands that read an input whose binding carries a caution (a proxy
such as interest expense for interest paid, or a derived value computed without some of its
components): such a band is not evaluable and must award 0 points rather than points earned
from a stand-in figure. The generated `Scores.lean` then subtracts exactly those band calls from
the policy's score, so Lean still computes the value, and `grade_steps` reads the grade
function's `if N ≤ score then "Label"` ladder so the grade is taken from the adjusted value.
`BAND_NOT_EVALUABLE` is the text the report shows for such a band.

Zeroing a band is only right for an additive points score. A score whose function is not a sum
of bands (a limit computation such as the maximum exposure) cannot drop a term, so
`not_evaluable_reason` says why such a score with a cautioned input is not evaluable at all;
the score then gets no value and the grade `SCORE_NOT_EVALUABLE`.
"""

import re
from dataclasses import dataclass, field

from busybee.schema.policy import BoundInput, ScoreSpec

BAND_NOT_EVALUABLE = "not evaluable (proxy)"
SCORE_NOT_EVALUABLE = "Not evaluable"
_PARAM_GROUP = re.compile(r"\(([^():]+):[^()]*\)")
_STEP = re.compile(r"if\s+(-?\d+)\s*≤\s*score\s+then\s+\"([^\"]+)\"")
_LAST = re.compile(r"else\s+\"([^\"]+)\"\s*$")


@dataclass(frozen=True)
class Band:
    """One band of a points score: the policy function and the parameters it reads."""

    function: str
    arguments: tuple[str, ...]

    @property
    def label(self) -> str:
        """The band's name for the report: the function name without its `_points` suffix."""
        return self.function.removesuffix("_points")


@dataclass
class ScoreAdjustment:
    """Bands a score must not count, and the grade ladder to grade the adjusted value with."""

    bands: list[Band] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    slot_of: dict[str, str] = field(default_factory=dict)
    steps: list[tuple[int, str]] = field(default_factory=list)
    floor: str = ""


def _definition(source: str, name: str) -> tuple[str, str] | None:
    """(header, body) of `def name`, the body running to the next unindented line."""
    start = re.search(rf"(?m)^def\s+{re.escape(name)}(?![\w'])", source)
    if start is None:
        return None
    assign = source.find(":=", start.end())
    if assign < 0:
        return None
    rest = source[assign + 2 :]
    end = re.search(r"\n(?=\S)", rest)
    return source[start.end() : assign], rest[: end.start()] if end else rest


def _parameters(header: str) -> list[str]:
    return [name for group in _PARAM_GROUP.findall(header) for name in group.split()]


def score_parameters(source: str, function: str) -> list[str]:
    """The parameter names of the score function, in order (empty when it is not found)."""
    found = _definition(source, function)
    return _parameters(found[0]) if found else []


def score_bands(source: str, function: str) -> list[Band]:
    """The band calls summed by the score function in the policy source (empty if none)."""
    found = _definition(source, function)
    if found is None:
        return []
    params = set(_parameters(found[0]))
    bands = []
    for term in found[1].split("+"):
        words = term.split()
        if len(words) > 1 and all(word in params for word in words[1:]):
            bands.append(Band(words[0], tuple(words[1:])))
    return bands


def grade_steps(source: str, function: str) -> tuple[list[tuple[int, str]], str]:
    """The `if N ≤ score then "Label"` ladder of the grade function and its last label."""
    found = _definition(source, f"{function}_grade")
    if found is None:
        return [], ""
    body = found[1].strip()
    last = _LAST.search(body)
    steps = [(int(value), label) for value, label in _STEP.findall(body)]
    return (steps, last.group(1)) if steps and last else ([], "")


def _reason(slot: str, item: BoundInput) -> str:
    return f"input {slot} is a proxy or misses components: {item.caution}"


def excluded_bands(spec: ScoreSpec, bound: list[BoundInput], source: str) -> ScoreAdjustment | None:
    """The bands of the score that read a cautioned input, with the grade ladder, else None."""
    cautioned = {item.slot: item for item in bound if item.caution}
    if not cautioned or not spec.lean_function:
        return None
    names = [slot.slot for slot in spec.inputs]
    params = score_parameters(source, spec.lean_function)
    slot_of = dict(zip(params, names, strict=True)) if len(params) == len(names) else {}
    adjustment = ScoreAdjustment(slot_of=slot_of)
    for band in score_bands(source, spec.lean_function):
        slots = [
            slot_of.get(name, name)
            for name in band.arguments
            if slot_of.get(name, name) in cautioned
        ]
        if slots:
            adjustment.bands.append(band)
            adjustment.reasons[band.label] = _reason(slots[0], cautioned[slots[0]])
    if not adjustment.bands:
        return None
    adjustment.steps, adjustment.floor = grade_steps(source, spec.lean_function)
    return adjustment


def not_evaluable_reason(spec: ScoreSpec, bound: list[BoundInput], source: str) -> str | None:
    """Why a non-additive score reading a cautioned input is not evaluable, else None."""
    cautioned = [item for item in bound if item.caution]
    if not cautioned or not spec.lean_function or score_bands(source, spec.lean_function):
        return None
    reasons = "; ".join(_reason(item.slot, item) for item in cautioned)
    return f"{spec.score_id} not evaluable: {reasons}"
