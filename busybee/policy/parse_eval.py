"""Parse the `#eval` stdout of a generated Scores.lean into values and grades per score.

The generated file prints `<score_id>=<value>` and `<score_id>_grade=<grade>`, one per line.
Score ids may themselves end in `_grade`, so lines are matched against the known score ids.
"""

import re
from dataclasses import dataclass

_LINE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<text>.*)$")
_GRADE_SUFFIX = "_grade"


@dataclass(frozen=True)
class ParsedScore:
    """The value and grade Lean printed for one score; either may be missing."""

    value: str | None = None
    grade: str | None = None


def parse_eval_output(stdout: str, score_ids: list[str]) -> dict[str, ParsedScore]:
    """Return the printed value and grade of every score id found in stdout."""
    known = set(score_ids)
    values: dict[str, str] = {}
    grades: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        match = _LINE.match(raw_line.strip())
        if match is None:
            continue
        key, text = match.group("key"), match.group("text").strip()
        if key in known:
            values[key] = text
        elif key.endswith(_GRADE_SUFFIX) and key[: -len(_GRADE_SUFFIX)] in known:
            grades[key[: -len(_GRADE_SUFFIX)]] = text
    return {
        score_id: ParsedScore(values.get(score_id), grades.get(score_id))
        for score_id in score_ids
        if score_id in values or score_id in grades
    }
