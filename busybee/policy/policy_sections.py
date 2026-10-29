"""Split a bank's policy.md into citable sections with stable ids P1, P2, and so on.

Every markdown heading (any level) starts a new section; text before the first heading becomes
a section headed "Preamble". Ids follow document order, so they stay stable while the policy
text is unchanged. Compose cites sections by id, and the renderer anchors each one on
`policy.html` as `id="P3"`, so a recommendation reason can open the exact clause.
"""

import re
from pathlib import Path

from pydantic import BaseModel

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


class PolicySection(BaseModel):
    """One heading-delimited section of the bank policy."""

    section_id: str
    heading: str
    text: str


def split_policy_sections(policy_md: str) -> list[PolicySection]:
    """Split policy markdown into sections at headings, ignoring headings inside code fences."""
    raw: list[tuple[str, list[str]]] = []
    heading, lines, fenced = "Preamble", [], False
    for line in policy_md.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        match = None if fenced else _HEADING.match(line)
        if match is None:
            lines.append(line)
            continue
        raw.append((heading, lines))
        heading, lines = match.group(2), []
    raw.append((heading, lines))
    kept = [(name, "\n".join(body).strip()) for name, body in raw]
    kept = [(name, text) for index, (name, text) in enumerate(kept) if text or index > 0]
    return [
        PolicySection(section_id=f"P{number}", heading=name, text=text)
        for number, (name, text) in enumerate(kept, start=1)
    ]


def load_policy_sections(banks_dir: str | Path, bank_id: str) -> list[PolicySection]:
    """Read banks/<bank_id>/policy.md and split it; an absent file gives no sections."""
    path = Path(banks_dir) / bank_id / "policy.md"
    if not path.is_file():
        return []
    return split_policy_sections(path.read_text(encoding="utf-8"))
