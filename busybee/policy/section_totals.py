"""Read a balance-sheet section total from the printed table, in code, checked against its rows.

Schedule III balance sheets often close a section (current assets, current liabilities,
non-current assets, non-current liabilities, equity) with a row of figures and no label, right
after the section's last row. The extractor skips such a row and the entailment judge cannot
confirm a label the passage does not print, so the slot stayed unbound although the figure is
on the page. `section_total` reads it deterministically: `page_lines` rebuilds the page from
its overlapping chunks (by character offsets, keeping each line once with the chunk that holds
it whole), the scan starts at the line that is the section heading ("Current assets", "Non
Current Liabilities", enumerators and leaders aside) and adds up every labelled row's figure in
the column whose header names the target year (a dash or Nil is zero, brackets negative). It
ends at the next section heading or at a statement total ("Total Assets", "Total Equity and
Liabilities"). A labelled row "Total <section>" is the section total as printed. An unlabelled
row whose figure equals the running sum of the rows above it (within the rounding of the
printed figures) is the section total; the last such row before the end is taken, so a nested
unlabelled subtotal (financial assets) is passed over. When the section has no total row at
all but ends cleanly on the page, the sum of its rows is the total, computed (`summed`) and
cited row by row. An unlabelled row that matches no running sum means the table was not read
as printed, and nothing is returned; so is a section that runs off the page or has no unit.

`section_total_fact` turns the reading into a `VerifiedFact` ("Consolidated total current
assets were INR 3,27,177 lakh as at March 31, 2026"), cited to the total row (and, when summed,
to every row) with the method `section_total_row` or `section_row_sum` and the rows in the
notes; there is no LLM entailment step because every quote is a line of the chunk and the
figure was checked in code. `section_total_facts` reads the facts for every unbound subtotal
slot of a binding (`components.SUBTOTAL_FORMULAS`) from the balance-sheet pages of the run's
basis; the slot search (`slot_search.fill_unbound_slots`) and `tools/replay_scores.py` use it
before any model reading, and `subtotals.subtotal_binding` binds the slot from the fact.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from busybee.policy.bind_inputs import BindingResult, score_input_slots
from busybee.policy.components import normalise_component, subtotal_formulas
from busybee.schema.documents import Chunk
from busybee.schema.facts import (
    Citation,
    FactCategory,
    FactScope,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.policy import ScoreSpec
from busybee.verify.numbers import numeric_values_from
from busybee.verify.table_units import chunk_unit

ADDED_BY = "slot_search"
ENTRY_PREFIX = "SLOT:S"
ROW_METHOD = "section_total_row"
SUM_METHOD = "section_row_sum"
SECTIONS = frozenset(
    {
        "non current assets",
        "current assets",
        "non current liabilities",
        "current liabilities",
        "equity",
    }
)
_STATEMENT_TOTALS = frozenset(
    {"assets", "liabilities", "equity and liabilities", "equity and liability"}
)
_ENUMERATOR = re.compile(r"^\s*(?:\(?(?:[a-h]|[ivx]{1,4}|i[a-z]|\d{1,2})[).]|[A-H]\.)\s*")
_FIGURE = re.compile(r"^\(?[-−]?\d[\d,]*(?:\.\d+)?\)?$")
_ZERO = re.compile(r"^(?:[-‐-―−]+|nil)$", re.IGNORECASE)
_DATE = re.compile(r"[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4}")
_BALANCE_SHEET = re.compile(r"balance\s+sheet", re.IGNORECASE)


@dataclass(frozen=True)
class Row:
    """One printed line of a section with its figure for the target year."""

    label: str
    printed: str
    value: Decimal
    line: str
    chunk: Chunk


@dataclass
class SectionTotal:
    """A section total as read: its row (None when summed), the rows it sums, the header."""

    section: str
    value: Decimal
    printed: str
    header: str
    total: Row | None
    rows: list[Row] = field(default_factory=list)

    @property
    def summed(self) -> bool:
        return self.total is None


def page_lines(chunks: list[Chunk]) -> list[tuple[str, Chunk]]:
    """The page's lines in order, each once, with a chunk that holds the whole line."""
    spans: list[tuple[int, int, str, Chunk]] = []
    for chunk in sorted(chunks, key=lambda c: (c.char_start, c.index_in_page)):
        at = 0
        for raw in chunk.text.split("\n"):
            start = chunk.char_start + at
            spans.append((start, start + len(raw), raw, chunk))
            at += len(raw) + 1
    kept: list[tuple[int, int, str, Chunk]] = []
    for span in sorted(spans, key=lambda s: (s[0], -(s[1] - s[0]))):
        if kept and span[0] >= kept[-1][0] and span[1] <= kept[-1][1]:
            continue
        kept.append(span)
    return [(line, chunk) for _, _, line, chunk in kept]


def _name(label: str) -> str:
    name = normalise_component(_ENUMERATOR.sub("", label))
    return name.removeprefix("total ").strip()


def _names_year(header: str, year: int) -> bool:
    return str(year) in header


def _figure(cell: str) -> Decimal | None:
    text = cell.strip()
    if _ZERO.match(text):
        return Decimal(0)
    if not _FIGURE.match(text):
        return None
    try:
        value = Decimal(text.strip("()").replace(",", "").replace("−", "-"))
    except InvalidOperation:
        return None
    return -abs(value) if text.startswith("(") else value


def _cell(line: str, year: int) -> tuple[str, str, str] | None:
    """(label, header, printed figure) of a table line's target-year cell, else None."""
    if " | " not in line and not re.match(r"^[^|]*:\s*\S", line):
        return None
    parts = [part.strip() for part in line.split(" | ")]
    first = parts[0]
    head, sep, value = first.rpartition(": ")
    label = "" if sep and _names_year(head, year) else first
    cells = parts if not label else parts[1:]
    for cell in cells:
        head, sep, value = cell.rpartition(": ")
        if sep and _names_year(head, year):
            return label, head.strip(), value.strip()
    return None


def _decimals(printed: str) -> int:
    return len(printed.rpartition(".")[2]) if "." in printed else 0


def _close(value: Decimal, rows: list[Row]) -> bool:
    places = max([_decimals(row.printed) for row in rows] or [0])
    tolerance = Decimal(len(rows)) * Decimal(5) / Decimal(10) ** (places + 1)
    return abs(value - sum((row.value for row in rows), Decimal(0))) <= tolerance


def section_total(lines: list[tuple[str, Chunk]], section: str, year: int) -> SectionTotal | None:
    """The total of the named balance-sheet section for the year, read from the lines, else None."""
    wanted = normalise_component(section)
    start = next(
        (i for i, (line, _) in enumerate(lines) if " | " not in line and _name(line) == wanted),
        None,
    )
    if start is None or not year:
        return None
    rows: list[Row] = []
    matches: list[tuple[Row, list[Row]]] = []
    ended = False
    header = ""
    for line, chunk in lines[start + 1 :]:
        text = line.strip()
        if text.startswith(("[TABLE", "[/TABLE")):
            continue
        cell = _cell(text, year)
        if cell is None:
            if _name(text) in SECTIONS | _STATEMENT_TOTALS and " | " not in text:
                ended = True
                break
            continue
        label, head, printed = cell
        value = _figure(printed)
        if value is None:
            return None
        header = header or head
        row = Row(label, printed, value, text, chunk)
        name = _name(label) if label else ""
        if label and name == wanted and normalise_component(label).startswith("total"):
            return SectionTotal(wanted, value, printed, head, row, rows)
        if label and (name in _STATEMENT_TOTALS or name in SECTIONS - {wanted}):
            ended = True
            break
        if label:
            rows.append(row)
            continue
        if not rows:
            return None
        if _close(value, rows):
            matches.append((row, list(rows)))
        elif not matches:
            return None
    if matches:
        row, summed = matches[-1]
        return SectionTotal(wanted, row.value, row.printed, header, row, summed)
    if ended and len(rows) >= 2:
        total = sum((row.value for row in rows), Decimal(0))
        places = max(_decimals(row.printed) for row in rows)
        printed = f"{total:,.{places}f}"
        return SectionTotal(wanted, total, printed, header, None, rows)
    return None


def _subject(section: str, basis: FactScope) -> str:
    words = section.replace("non current", "non-current")
    lead = "Consolidated total" if basis is FactScope.consolidated else "Total"
    return f"{lead} {words}"


def section_total_fact(
    found: SectionTotal, page: list[Chunk], basis: FactScope, entry_id: str
) -> VerifiedFact | None:
    """The verified fact stating the section total, cited to its rows, else None (no unit)."""
    anchor = found.total or found.rows[-1]
    unit = chunk_unit(anchor.chunk, page, anchor.line)
    if not unit:
        return None
    dated = _DATE.search(found.header)
    when = f"as at {dated.group(0)}" if dated else f"in {found.header}"
    verb = "was" if found.section == "equity" else "were"
    statement = f"{_subject(found.section, basis)} {verb} INR {found.printed} {unit} {when}"
    listed = "; ".join(f"{row.label} {row.printed}" for row in found.rows)
    if found.summed:
        statement += f", the sum of the {len(found.rows)} rows of the section"
        notes = f"computed: sum of the section's printed rows ({listed})"
        cited = found.rows
    else:
        how = "labelled" if found.total.label else "unlabelled"
        notes = (
            f"{how} total row closing the {found.section} section of the balance sheet; "
            f"equals the sum of its rows ({listed})"
        )
        cited = [found.total]
    citations = [
        Citation(
            chunk_id=r.chunk.chunk_id, doc_id=r.chunk.doc_id, page_no=r.chunk.page_no, quote=r.line
        )
        for r in cited
    ]
    return VerifiedFact(
        fact_id="",
        statement=f"{statement}.",
        category=FactCategory.liquidity,
        citations=citations,
        numbers=numeric_values_from(statement),
        verification=Verification(
            status=VerificationStatus.supported,
            method=SUM_METHOD if found.summed else ROW_METHOD,
            notes=notes,
        ),
        importance=4,
        source_entry_id=entry_id,
        added_by=ADDED_BY,
        scope=basis,
    )


def balance_sheet_pages(
    chunks: list[Chunk], bases: dict[tuple[str, int], str], basis: FactScope
) -> list[list[Chunk]]:
    """The chunks of each balance-sheet page of the basis, pages in document order."""
    pages: dict[tuple[str, int], list[Chunk]] = {}
    for chunk in chunks:
        pages.setdefault((chunk.doc_id, chunk.page_no), []).append(chunk)
    return [
        pages[key]
        for key in sorted(pages)
        if bases.get(key) == basis.value and any(_BALANCE_SHEET.search(c.text) for c in pages[key])
    ]


def read_section_total(
    section: str,
    chunks: list[Chunk],
    bases: dict[tuple[str, int], str],
    basis: FactScope,
    year: int,
    entry_id: str,
) -> VerifiedFact | None:
    """The first balance-sheet page of the basis that yields the section total, as a fact."""
    for page in balance_sheet_pages(chunks, bases, basis):
        found = section_total(page_lines(page), section, year)
        if found is not None:
            fact = section_total_fact(found, page, basis, entry_id)
            if fact is not None:
                return fact
    return None


def section_total_facts(
    specs: list[ScoreSpec],
    binding: BindingResult,
    chunks: list[Chunk],
    bases: dict[tuple[str, int], str],
    year: int,
) -> dict[str, VerifiedFact]:
    """For every unbound subtotal slot, the section total read from the pages, by slot name."""
    found: dict[str, VerifiedFact] = {}
    for spec, slot in score_input_slots(specs):
        if (spec.score_id, slot.slot) not in binding.unbound or slot.slot in found:
            continue
        if not subtotal_formulas(slot):
            continue
        entry_id = f"{ENTRY_PREFIX}{len(found) + 1:03d}"
        section = slot.slot.replace("_", " ")
        fact = read_section_total(section, chunks, bases, binding.basis, year, entry_id)
        if fact is not None:
            found[slot.slot] = fact
    return found
