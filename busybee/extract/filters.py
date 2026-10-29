"""Drop extracted entries that are meta-commentary instead of facts about the borrower.

The extractor sometimes records what the passages do NOT say ("the provided passages do not
mention covenants", "no information is available"). Such an entry can never be verified against
a source and only pollutes the report. `drop_meta_commentary` splits entries into kept ones and
`DroppedEntry` records with stage `extract.filter`, which `run_extract` writes to `dropped.json`
before the entries reach verify and its dedupe.
"""

import re
from collections.abc import Iterable

from busybee.schema.facts import DroppedEntry, NotebookEntry

STAGE_FILTER = "extract.filter"
_META = re.compile(
    r"\bthe\s+(?:provided\s+)?passages?\b|\bthe\s+document\s+does\s+not\s+mention\b"
    r"|\bnot\s+specified\s+in\b|\bno\s+information\s+(?:is\s+)?available\b",
    re.IGNORECASE,
)


def is_meta_commentary(statement: str) -> bool:
    """Return True when the statement talks about the passages instead of the borrower."""
    return _META.search(statement) is not None


def drop_meta_commentary(
    entries: Iterable[NotebookEntry],
) -> tuple[list[NotebookEntry], list[DroppedEntry]]:
    """Return (kept entries, dropped records) with meta-commentary entries removed."""
    kept: list[NotebookEntry] = []
    dropped: list[DroppedEntry] = []
    for entry in entries:
        if is_meta_commentary(entry.statement):
            reason = "meta-commentary about the passages, not a fact"
            dropped.append(DroppedEntry(entry=entry, reason=reason, stage=STAGE_FILTER))
        else:
            kept.append(entry)
    return kept, dropped
