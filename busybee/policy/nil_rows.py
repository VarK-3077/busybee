"""Statement rows printed as a dash or "Nil" for the target period are a stated zero.

In Indian financial statements a row whose value cell is "-", an en or em dash, or "Nil" means
the line item is zero, not that the figure is missing. The slot search uses this module as a
deterministic fallback after the model found nothing in a hit: `nil_row_entry` reads the
chunk's table lines ("<row label> | <column header>: <cell> | ..."), finds a row whose label
has the same words as the wanted line item (or one of its other wordings), and checks that the
cell under the column header naming the target year is a dash or Nil. Only then it writes a
`NotebookEntry` whose statement reads "Current investments were nil (INR 0 crore) as at March
31, 2026", cited to the chunk with the row line as the verbatim quote. The unit is the table
header's (`chunk_unit`); zero is unit-free, so crore is used when the page prints none. A dash
in the prior-year column only, a row absent from the page, or a table without named columns
yields nothing. `nil_fact` turns such an entry into a `VerifiedFact` without the LLM
entailment step (the quote is a line of the chunk by construction, and the number check cannot
see a zero in a dash); entries of this kind are recognised by `is_nil_entry`.
"""

import re

from busybee.policy.components import item_wordings
from busybee.schema.documents import Chunk
from busybee.schema.facts import (
    Citation,
    FactCategory,
    NotebookEntry,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.verify.numbers import numeric_values_from

NIL_PREFIX = "SLOT:N"
NIL_METHOD = "nil_row_match"
DEFAULT_UNIT = "crore"
_ZERO_CELL = re.compile(r"^\s*(?:[-‐-―−]+|nil)\s*$", re.IGNORECASE)
_ENUMERATOR = re.compile(r"^\s*\((?:[a-z]|[ivx]+|\d+)\)\s*", re.IGNORECASE)
_DROPPED_WORDS = frozenset({"total", "the"})
_FLOW_LABEL = re.compile(r"\b(paid|(?:re)?payments?|proceeds|taxes)\b", re.IGNORECASE)
_DATED_HEADER = re.compile(
    r"[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4}", re.IGNORECASE
)


def is_nil_entry(entry: NotebookEntry) -> bool:
    """True for an entry written by `nil_row_entry`."""
    return entry.entry_id.startswith(NIL_PREFIX)


def _words(label: str) -> frozenset[str]:
    found = re.findall(r"[a-z]+", label.lower())
    return frozenset(w.removesuffix("s") for w in found if len(w) > 1 and w not in _DROPPED_WORDS)


def _names_year(header: str, year: int) -> bool:
    if str(year) in header:
        return True
    short = f"{year % 100:02d}"
    return bool(re.search(rf"\b(?:19|20)\d\d\s?[-–/]\s?{short}\b|\bFY\s?{short}\b", header, re.I))


def _cells(line: str) -> tuple[str, list[tuple[str, str]]]:
    label, *cells = [part.strip() for part in line.split(" | ")]
    split = [cell.rpartition(": ") for cell in cells]
    return _ENUMERATOR.sub("", label.rsplit(" / ", 1)[-1]), [
        (head.strip(), value) for head, sep, value in split if sep
    ]


def _nil_line(chunk: Chunk, wordings: set[frozenset[str]], year: int) -> tuple[str, str] | None:
    """(row line, column header) of the first row with a wanted label and a zero cell for year."""
    for raw in chunk.text.splitlines():
        line = raw.strip()
        if " | " not in line or line.startswith("[TABLE:"):
            continue
        label, cells = _cells(line)
        if _words(label) not in wordings:
            continue
        for head, value in cells:
            if _names_year(head, year):
                if _ZERO_CELL.match(value):
                    return line, head
                break
    return None


def _period_phrase(phrase: str, header: str, year: int) -> str:
    dated = _DATED_HEADER.search(header)
    when = dated.group(0) if dated else f"FY{year}"
    if _FLOW_LABEL.search(phrase):
        return f"for the year ended {when}" if dated else f"for {when}"
    return f"as at {when}" if dated else f"in {when}"


def nil_row_entry(
    chunk: Chunk,
    phrase: str,
    year: int,
    unit: str,
    basis: str,
    entry_id: str,
    category: FactCategory,
    importance: int,
    added_by: str,
) -> NotebookEntry | None:
    """An entry stating the line item as nil for `year` when the chunk has such a row, else None."""
    if not year:
        return None
    wordings = {_words(w) for w in item_wordings(phrase)} - {frozenset()}
    found = _nil_line(chunk, wordings, year)
    if found is None:
        return None
    line, header = found
    label = _cells(line)[0]
    verb = "were" if label.rstrip().lower().endswith("s") else "was"
    subject = f"Consolidated {label[:1].lower()}{label[1:]}" if basis == "consolidated" else label
    statement = (
        f"{subject[:1].upper()}{subject[1:]} {verb} nil (INR 0 {unit or DEFAULT_UNIT}) "
        f"{_period_phrase(phrase, header, year)}"
    )
    citation = Citation(
        chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no, quote=line
    )
    return NotebookEntry(
        entry_id=entry_id.replace("SLOT:E", NIL_PREFIX),
        statement=statement,
        citations=[citation],
        category=category,
        doc_id=chunk.doc_id,
        importance=importance,
        added_by=added_by,
    )


def nil_fact(entry: NotebookEntry) -> VerifiedFact:
    """The verified fact for a nil-row entry: deterministic, the quote is a line of the chunk."""
    return VerifiedFact(
        fact_id="",
        statement=entry.statement,
        category=entry.category,
        citations=entry.citations,
        numbers=numeric_values_from(entry.statement),
        verification=Verification(
            status=VerificationStatus.supported,
            method=NIL_METHOD,
            notes="row printed as a dash or Nil in the target-period column of the cited table",
        ),
        importance=entry.importance,
        source_entry_id=entry.entry_id,
        added_by=entry.added_by,
    )
