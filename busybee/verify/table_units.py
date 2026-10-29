"""The money unit a table figure is printed in, read from its table or page header.

Annual reports print the scale once, above a table or at the top of the page: "(₹ in lakhs)",
"(Rs. crore)", "INR million", "(All amounts in INR lakhs, unless otherwise stated)", "₹ '000".
The rupee sign is often extracted as a stray letter or backtick ("(H in lakhs)", "(D in Crores)",
"(` in lakhs)"), so a single capital letter or mark before "in" also counts. `last_unit` reads
the last such header in a text and `chunk_unit` the one a row of a chunk sits under: the table
prefix, the chunk text above the quoted row, then earlier chunks of the same page (nearest
first), and only then the rest of the chunk.

`with_header_units` makes the unit of every money figure a fact takes from a table row
deterministic: when a citation's quote lies inside a `[TABLE]` block and the page names a unit,
each fact number with a money scale (lakh, crore, million, billion, thousand), its own or the
one the statement prints after it ("1,155.73 INR crore"), whose figure is printed in that quote
takes the header's scale, whatever the model wrote. A quoted row that names its own unit
("Revenue Rs million | FY19: 10,835.2") keeps it: the row outranks a header. The record unit and
the statement's unit word follow, and the verification notes say what changed. A figure the
model converted itself (3,264.06 crore for a printed 3,26,406) is not in the quote and is left
alone; a number without a scale word (a ratio, a per-share amount) is never touched. Both the
extract and the slot-search facts pass through it at the end of `verify_entries`.
"""

import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal

from busybee.schema.documents import Chunk
from busybee.schema.facts import NumericValue, Verification, VerificationStatus, VerifiedFact

from .number_match import UNIT_ALIASES, find_numbers

logger = logging.getLogger(__name__)

MONEY_MARK = r"(?:₹|`|Rs\.?|INR|Rupees)"
UNIT_HEADER = re.compile(
    rf"(?:(?:amounts?|figures?)\s+(?:are\s+)?(?:stated\s+)?in\s+|{MONEY_MARK}\s*(?:in\s+)?"
    rf"|\(\s*(?:[A-Z]|[^\w\s()])\s+in\s+|\(\s*in\s+)(?:{MONEY_MARK}\s*)?"
    r"(lakhs?|lacs?|crores?|cr\b|millions?|mn\b|billions?|bn\b|thousands?|['’]000)",
    re.IGNORECASE,
)
_UNIT_NAMES = {
    "lac": "lakh",
    "cr": "crore",
    "mn": "million",
    "bn": "billion",
    "'000": "thousand",
    "’000": "thousand",
}
_SCALES = frozenset({"lakh", "crore", "million", "billion", "thousand"})
_UNIT_WORD = r"(?:lakhs?|lacs?|crores?|crs?|millions?|mn|billions?|bn|thousands?)(?![A-Za-z])"
_ROW_UNIT = re.compile(rf"(?<![A-Za-z]){_UNIT_WORD}", re.IGNORECASE)
HEADER_METHOD_NOTE = "unit from table header"


def unit_word(raw: str) -> str:
    """Canonical singular unit word: 'Lakhs' -> 'lakh', 'Mn' -> 'million', "'000" -> 'thousand'."""
    word = raw.lower().rstrip(".")
    word = _UNIT_NAMES.get(word, word)
    return word[:-1] if word.endswith("s") else word


def last_unit(text: str) -> str:
    """The unit named by the last unit header in the text, else ''."""
    found = list(UNIT_HEADER.finditer(text))
    return unit_word(found[-1].group(1)) if found else ""


def chunk_unit(chunk: Chunk, page_chunks: Iterable[Chunk], quote: str = "") -> str:
    """The money unit a table row is printed in, read from the headers above it, else ''."""
    at = chunk.text.find(quote) if quote else -1
    above = chunk.text[: at if at >= 0 else len(chunk.text)]
    unit = last_unit(chunk.prefix) or last_unit(above)
    if unit:
        return unit
    earlier = sorted(
        (c for c in page_chunks if c.index_in_page < chunk.index_in_page),
        key=lambda c: -c.index_in_page,
    )
    for other in earlier:
        unit = last_unit(f"{other.prefix}\n{other.text}")
        if unit:
            return unit
    return last_unit(chunk.text)


def in_table_block(chunk: Chunk, quote: str) -> bool:
    """True when the quote lies inside a [TABLE] block of the chunk (or one the chunk opens in)."""
    at = chunk.text.find(quote) if quote else -1
    if at < 0:
        return False
    before = chunk.text[:at]
    opened = before.rfind("[TABLE:")
    closed = before.rfind("[/TABLE]")
    if opened > closed:
        return True
    return closed < 0 and chunk.prefix.startswith("[TABLE")


def page_index(chunks: Iterable[Chunk]) -> dict[tuple[str, int], list[Chunk]]:
    """Chunks grouped by (doc_id, page_no)."""
    pages: dict[tuple[str, int], list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        pages[(chunk.doc_id, chunk.page_no)].append(chunk)
    return pages


def _scale_of(unit: str) -> str:
    return next(
        (UNIT_ALIASES[w] for w in unit.lower().split() if UNIT_ALIASES.get(w) in _SCALES), ""
    )


def _printed(value: Decimal, quote: str) -> bool:
    wanted = abs(value)
    return any(abs(mention.value) == wanted for mention in find_numbers(quote))


def _with_scale(unit: str, scale: str) -> str:
    words = [scale if UNIT_ALIASES.get(w.lower()) in _SCALES else w for w in unit.split()]
    return " ".join(words)


def _unit_after(statement: str, value: Decimal) -> re.Match[str] | None:
    digits = format(abs(value), "f")
    loose = ",?".join(re.escape(char) for char in digits)
    pattern = rf"(?<![\d,.])({loose})(\s*(?:(?:INR|Rs\.?|₹)\s*)?)({_UNIT_WORD})"
    return re.search(pattern, statement, re.IGNORECASE)


def statement_scale(statement: str, value: Decimal) -> str:
    """The money scale the statement prints right after the figure `value`, else ''."""
    found = _unit_after(statement, value)
    return UNIT_ALIASES.get(found.group(3).lower(), "") if found else ""


def restate_unit(statement: str, value: Decimal, new: str) -> str:
    """Replace the unit word printed right after the figure `value` in the statement."""
    found = _unit_after(statement, value)
    if found is None:
        return statement
    start, end = found.span(3)
    return f"{statement[:start]}{new}{statement[end:]}"


def _header_units(fact: VerifiedFact, chunks: Mapping[str, Chunk], pages: Mapping) -> list[str]:
    """For each citation in a table under a unit header, that header's unit per quote."""
    found = []
    for citation in fact.citations:
        chunk = chunks.get(citation.chunk_id)
        if chunk is None or not in_table_block(chunk, citation.quote):
            continue
        if _ROW_UNIT.search(citation.quote):
            continue
        unit = chunk_unit(chunk, pages.get((chunk.doc_id, chunk.page_no), []), citation.quote)
        if unit:
            found.append((citation.quote, unit))
    return found


def with_header_units(
    fact: VerifiedFact, chunks: Mapping[str, Chunk], pages: Mapping | None = None
) -> VerifiedFact:
    """The fact with every table figure in its table header's money unit, the change noted."""
    pages = pages if pages is not None else page_index(chunks.values())
    headers = _header_units(fact, chunks, pages)
    if not headers:
        return fact
    numbers: list[NumericValue] = []
    statement = fact.statement
    changes: list[str] = []
    swaps: dict[Decimal, tuple[str, str]] = {}
    for number in fact.numbers:
        scale = _scale_of(number.unit) or statement_scale(statement, number.value)
        header = next((unit for quote, unit in headers if _printed(number.value, quote)), "")
        if not scale or not header or header == scale:
            numbers.append(number)
            continue
        unit = _with_scale(number.unit, header) if _scale_of(number.unit) else f"INR {header}"
        numbers.append(number.model_copy(update={"unit": unit}))
        statement = restate_unit(statement, number.value, header)
        swaps[abs(number.value)] = (scale, header)
        changes.append(f"{number.value} {scale} -> {header}")
    if not changes:
        return fact
    record = fact.record
    if record is not None and abs(record.value) in swaps and _scale_of(record.unit):
        record = record.model_copy(
            update={"unit": _with_scale(record.unit, swaps[abs(record.value)][1])}
        )
    note = f"{HEADER_METHOD_NOTE} (model unit overridden: {', '.join(changes)})"
    verification = fact.verification or Verification(status=VerificationStatus.supported)
    verification = verification.model_copy(
        update={"notes": "; ".join(p for p in (verification.notes, note) if p)}
    )
    logger.info("fact %s: %s", fact.fact_id or fact.source_entry_id, note)
    return fact.model_copy(
        update={
            "numbers": numbers,
            "statement": statement,
            "record": record,
            "verification": verification,
        }
    )


def facts_with_header_units(
    facts: Iterable[VerifiedFact], chunks: Mapping[str, Chunk]
) -> list[VerifiedFact]:
    """Every fact through `with_header_units`, sharing one page index."""
    pages = page_index(chunks.values())
    return [with_header_units(fact, chunks, pages) for fact in facts]
