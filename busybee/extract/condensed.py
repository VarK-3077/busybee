"""Render the rolling notebook as compact one-line entries for the next LLM window."""

from collections.abc import Iterable

from busybee.schema.facts import NotebookEntry

STATEMENT_LIMIT = 160


def _single_line(text: str) -> str:
    """Collapse whitespace so one entry always occupies exactly one line."""
    return " ".join(text.split())


def condense_entry(entry: NotebookEntry, statement_limit: int = STATEMENT_LIMIT) -> str:
    """Render one entry as id, category, importance, truncated statement, and citations."""
    statement = _single_line(entry.statement)[:statement_limit]
    cites = ", ".join(citation.chunk_id for citation in entry.citations) or "none"
    return (
        f"{entry.entry_id} | {entry.category.value} | imp {entry.importance} | "
        f"{statement} | cites {cites}"
    )


def condense_notebook(
    entries: Iterable[NotebookEntry],
    statement_limit: int = STATEMENT_LIMIT,
) -> str:
    """Render every entry as one compact line, preserving notebook order."""
    return "\n".join(condense_entry(entry, statement_limit=statement_limit) for entry in entries)
