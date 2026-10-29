"""Find the statement heading path a table row sits under, so records know their section.

A balance sheet repeats row labels under different headings (Investments appears under both
"Non Current Assets > Financial Assets" and "Current Assets > Financial Assets"), and only the
heading says which one a figure is. `record_section` reads the chunks that hold a record's row,
plus up to two pages before them for a table that continues across a page break, and walks the
text line by line. A short line without a column separator is a heading: one with no
enumerator ("Non Current Assets") replaces the path, a lettered one ("(f) Financial Assets")
becomes the second level, which the next lettered or total row closes; roman-numbered rows
(i), (ii) belong to the open second level. The row is found by its label (enumerator and dot
leaders removed), preferring the row whose cells print the record's value. The result is the
path joined with " > ", or None when no heading or no row is found.
`section_phrase` turns a section into the words a statement carries: "non-current" or
"current" when the path starts under Non Current/Current Assets or Liabilities.
"""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal

from busybee.schema.documents import Chunk

_LOOKBACK_PAGES = 2
_MAX_HEADING_CHARS = 70
_MAX_SECTION_CHARS = 120
_SEPARATOR = " > "
_ENUMERATOR = re.compile(r"^\(([a-z0-9]{1,4})\)\s*|^(?:[A-Z]|[IVX]{1,4}|\d{1,2})[.)]\s+")
_LETTERED = re.compile(r"^\(([a-z])\)\s")
_ROMAN = re.compile(r"^\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\)\s")
_LEADER = re.compile(r"\s*\.{2,}\s*")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_BALANCE_SHEET_SIDE = re.compile(r"\b(non[- ]?current|current)\s+(assets|liabilities)\b", re.I)


def _clean(text: str) -> str:
    text = _LEADER.sub(" ", text).strip(" \t:.-")
    return _ENUMERATOR.sub("", text).strip(" \t:.-")


def _normal(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(label).lower()).strip()


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    return (
        bool(stripped)
        and " | " not in stripped
        and not stripped.startswith("[")
        and len(stripped) <= _MAX_HEADING_CHARS
        and not stripped.endswith((".", ",", ";"))
        and any(ch.isalpha() for ch in stripped)
    )


def _joined(path: Sequence[str]) -> str | None:
    text = _SEPARATOR.join(part for part in path if part)
    return text[:_MAX_SECTION_CHARS] or None


class _Row:
    __slots__ = ("cells", "label", "section")

    def __init__(self, label: str, cells: str, section: str | None) -> None:
        self.label = label
        self.cells = cells
        self.section = section


def _walk(text: str, path: list[str]) -> list[_Row]:
    """Rows of one chunk with their section, updating `path` (two levels) in place."""
    rows: list[_Row] = []
    for line in text.splitlines():
        if _is_heading(line):
            cleaned = _clean(line)
            if not cleaned:
                continue
            if _LETTERED.match(line.strip()) and path[0]:
                path[1] = cleaned
            elif not _ROMAN.match(line.strip()):
                path[0], path[1] = cleaned, ""
            continue
        if " | " not in line or line.startswith("[TABLE:"):
            continue
        label, _, cells = line.partition(" | ")
        if not _ROMAN.match(label.strip()):
            path[1] = ""
        rows.append(_Row(label, cells, _joined(path)))
    return rows


def _numbers_in(cells: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in _NUMBER.findall(cells):
        try:
            values.add(Decimal(token.replace(",", "")))
        except ArithmeticError:
            continue
    return values


def _pages_before(chunk: Chunk, chunks_by_id: Mapping[str, Chunk]) -> list[Chunk]:
    nearby = [
        other
        for other in chunks_by_id.values()
        if other.doc_id == chunk.doc_id
        and chunk.page_no - _LOOKBACK_PAGES <= other.page_no <= chunk.page_no
    ]
    nearby.sort(key=lambda other: (other.page_no, other.index_in_page))
    return nearby


def record_section(
    metric: str,
    value: Decimal,
    chunk_ids: Sequence[str],
    chunks_by_id: Mapping[str, Chunk],
) -> str | None:
    """The heading path of the row labelled `metric` printing `value` in the cited chunks."""
    wanted = _normal(metric)
    cited = {chunk_id for chunk_id in chunk_ids if chunk_id in chunks_by_id}
    if not wanted or not cited:
        return None
    anchor = chunks_by_id[sorted(cited)[0]]
    matches: list[_Row] = []
    path = ["", ""]
    for chunk in _pages_before(anchor, chunks_by_id):
        rows = _walk(chunk.text, path)
        if chunk.chunk_id in cited:
            matches.extend(row for row in rows if _normal(row.label) == wanted)
    if not matches:
        return None
    for row in matches:
        if value in _numbers_in(row.cells) or -value in _numbers_in(row.cells):
            return row.section
    return matches[0].section


def section_phrase(section: str | None) -> str:
    """ "non-current" or "current" for a path under Non Current/Current Assets or Liabilities."""
    if not section:
        return ""
    match = _BALANCE_SHEET_SIDE.search(section.split(_SEPARATOR)[0])
    if match is None:
        return ""
    return "non-current" if match.group(1).lower().startswith("non") else "current"
