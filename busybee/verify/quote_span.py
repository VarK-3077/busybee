"""Deterministic citation quote for a verdict that came from a classifier, which writes no text.

`deterministic_quote(statement, chunk_text)` returns a verbatim line of the chunk: the first line
holding one of the statement's numbers (the same rule the adjacent-chunk path uses), else the line
sharing the most content tokens with the statement, else the chunk's first non-empty line. The
result is always a substring of the chunk and never empty for a non-empty chunk.
"""

import re

from .number_match import find_numbers

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP_WORDS = frozenset(
    "the and for with that this from were was are has had have its our their which been "
    "during into over than also not but per all any may can will year years company".split()
)


def _content_tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(text.casefold())) - _STOP_WORDS


def token_overlap(statement: str, line: str) -> float:
    """Share of the statement's content tokens that also occur in line (0.0 when it has none)."""
    wanted = _content_tokens(statement)
    return len(wanted & _content_tokens(line)) / len(wanted) if wanted else 0.0


def deterministic_quote(statement: str, chunk_text: str) -> str:
    """Pick the chunk line that best stands for the evidence of statement."""
    lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
    if not lines:
        return chunk_text.strip()
    for mention in find_numbers(statement):
        for line in lines:
            if mention.text in line:
                return line
    wanted = _content_tokens(statement)
    best = max(lines, key=lambda line: len(wanted & _content_tokens(line)))
    return best if wanted & _content_tokens(best) else lines[0]
