"""Windowing of long chunk text around the evidence, shared by the eval harness and verify.

`anchor_offset` finds where the evidence sits in a text: the middle of the quote when it occurs,
else the first statement number that occurs, else 0. `window_around_numbers` cuts at most
`max_chars` of the text centred on the first statement number found in it (the whole text when it
is short enough), so classifier models with a 512-1024 token limit see the relevant lines.
"""

import re

from .number_match import find_numbers

CLASSIFIER_WINDOW_CHARS = 1500


def anchor_offset(text: str, quote: str, statement: str) -> int:
    """Return the offset in text of the quote, else of the first statement number, else 0."""
    words = quote.split()
    if words:
        match = re.search(r"\s+".join(re.escape(w) for w in words), text)
        if match:
            return (match.start() + match.end()) // 2
    for mention in find_numbers(statement):
        at = text.find(mention.text)
        if at >= 0:
            return at + len(mention.text) // 2
    return 0


def window_around_numbers(
    text: str, statement: str, max_chars: int = CLASSIFIER_WINDOW_CHARS
) -> str:
    """Return text if it fits in max_chars, else a window centred on the first statement number."""
    if len(text) <= max_chars:
        return text
    centre = anchor_offset(text, "", statement)
    start = max(0, min(centre - max_chars // 2, len(text) - max_chars))
    return text[start : start + max_chars]
