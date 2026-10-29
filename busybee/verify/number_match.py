"""Deterministic number matching between a statement and the text that is cited for it.

`find_numbers` scans text for numeric mentions and understands western and Indian digit
grouping (1,234,567 and 1,23,456.78), percentages, parenthesised negatives, currency marks,
magnitude words (crore, lakh, million, billion, thousand) and fiscal-year tokens (FY24 also
stands for 2024). Every mention carries all values it can be read as: the raw number and, when a
magnitude word follows, the unit-normalised number. `statement_numbers_supported` then checks
that each number of a statement occurs somewhere in the cited text, comparing absolute values
so that sign conventions and grouping or decimal formatting never cause a false alarm.
Numbers that are parts of dates ("March 31, 2026", "31st March 2026", "31.03.2026") are not
required as standalone numbers: a statement date is satisfied by any rendering of the same
day-month-year in the cited text, and a fiscal range such as FY2025-26 by any of its years.
Letters directly before a digit (D1, Q3, p214) mark identifiers, so those digits are ignored.

With `require_period_adjacency=True` (used when evidence is stitched from neighbouring chunks)
a statement that names a period (FY token, year, quarter, "as at/of <date>") only counts a
number as supported when a period token occurs within 120 characters of it in the cited text,
so a bare figure from an unrelated column or year cannot satisfy it.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

UNIT_MULTIPLIERS: dict[str, Decimal] = {
    "crore": Decimal(10) ** 7,
    "lakh": Decimal(10) ** 5,
    "million": Decimal(10) ** 6,
    "billion": Decimal(10) ** 9,
    "thousand": Decimal(10) ** 3,
}
UNIT_ALIASES: dict[str, str] = {
    "crore": "crore",
    "crores": "crore",
    "cr": "crore",
    "crs": "crore",
    "lakh": "lakh",
    "lakhs": "lakh",
    "lac": "lakh",
    "lacs": "lakh",
    "million": "million",
    "millions": "million",
    "mn": "million",
    "billion": "billion",
    "billions": "billion",
    "bn": "billion",
    "thousand": "thousand",
    "thousands": "thousand",
}
_NUMBER = re.compile(r"(?<![A-Za-z0-9])(?<!\d[.,])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
_FISCAL = re.compile(
    r"(?<![A-Za-z])(?:FY|CY)\s?'?(\d{4}|\d{2})(?!\d)(?:\s?[-–/]\s?(\d{4}|\d{2})(?!\d))?",
    re.IGNORECASE,
)
_SUFFIX = re.compile(
    r"^(?:\s?(?P<pct>%)|\s?(?P<unit>crores?|crs?|lakhs?|lacs?|millions?|mn|billions?|bn"
    r"|thousands?)(?![A-Za-z]))",
    re.IGNORECASE,
)
_PERIOD = re.compile(
    r"(?:FY|CY)\s?'?\d{2,4}|(?<!\d)(?:19|20)\d{2}(?!\d)|(?<![A-Za-z0-9])Q[1-4](?!\d)"
    r"|\bas\s+(?:at|of)\s+\w+",
    re.IGNORECASE,
)
_MONTHS = (
    "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    "sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_DAY_MONTH_YEAR = re.compile(
    rf"(?<![\w.])(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTHS})\b\.?,?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_MONTH_DAY_YEAR = re.compile(
    rf"\b({_MONTHS})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"(?<![\d.])(\d{1,2})([./-])(\d{1,2})\2(\d{4}|\d{2})(?![\d])")
_ISO_DATE = re.compile(r"(?<![\d.])(\d{4})-(\d{2})-(\d{2})(?!\d)")
PERIOD_WINDOW = 120
_CURRENCY = re.compile(r"(?:₹|Rs\.?|INR|US\$|USD|\$)\s?$", re.IGNORECASE)


@dataclass(frozen=True)
class NumberMention:
    """One numeric mention with every value it may be read as."""

    text: str
    start: int
    end: int
    value: Decimal
    unit: str = ""
    percent: bool = False
    currency: str = ""
    fiscal: bool = False
    alternatives: tuple[Decimal, ...] = field(default_factory=tuple)


def _decimal(token: str) -> Decimal | None:
    try:
        return Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None


def _fiscal_alternatives(token: str) -> tuple[Decimal, ...]:
    year = Decimal(token)
    return (year,) if len(token) == 4 else (year, Decimal(2000) + year)


def _fiscal_mentions(text: str) -> list[NumberMention]:
    mentions: list[NumberMention] = []
    for match in _FISCAL.finditer(text):
        for group in (1, 2):
            token = match.group(group)
            if token is None:
                continue
            alternatives = _fiscal_alternatives(token)
            mentions.append(
                NumberMention(
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    value=alternatives[-1],
                    fiscal=True,
                    alternatives=alternatives,
                )
            )
    return mentions


def _is_negative(before: str, after: str) -> bool:
    """Negative when written as (123), or with a leading minus that is not a range dash."""
    stripped = before.rstrip()
    if stripped.endswith("(") and after.lstrip().startswith(")"):
        return True
    if stripped and stripped[-1] in "-\u2212\u2013":
        previous = stripped[-2] if len(stripped) > 1 else " "
        return not previous.isalnum()
    return False


def _mention_at(
    text: str, match: re.Match[str], taken: list[tuple[int, int]]
) -> NumberMention | None:
    start, end = match.span()
    if any(low <= start < high for low, high in taken):
        return None
    raw = _decimal(match.group(1))
    if raw is None:
        return None
    suffix = _SUFFIX.match(text[end:])
    percent = bool(suffix and suffix.group("pct"))
    unit = ""
    if suffix and suffix.group("unit"):
        unit = UNIT_ALIASES[suffix.group("unit").lower()]
    mention_end = end + (suffix.end() if suffix else 0)
    before = text[:start]
    currency_match = _CURRENCY.search(before)
    currency = currency_match.group(0).strip() if currency_match else ""
    mention_start = currency_match.start() if currency_match else start
    negative = _is_negative(text[:mention_start], text[mention_end:])
    value = -raw if negative else raw
    alternatives = [value]
    if unit:
        alternatives.append(value * UNIT_MULTIPLIERS[unit])
    return NumberMention(
        text=text[mention_start:mention_end].strip(),
        start=mention_start,
        end=mention_end,
        value=value,
        unit=unit,
        percent=percent,
        currency=currency,
        alternatives=tuple(alternatives),
    )


def find_numbers(text: str) -> list[NumberMention]:
    """Return every numeric mention in text, in reading order."""
    fiscal = _fiscal_mentions(text)
    taken = [(mention.start, mention.end) for mention in fiscal]
    mentions = list(fiscal)
    for match in _NUMBER.finditer(text):
        mention = _mention_at(text, match, taken)
        if mention is not None:
            mentions.append(mention)
    return sorted(mentions, key=lambda mention: (mention.start, mention.end))


def extract_numbers(text: str) -> list[Decimal]:
    """Return the raw and unit-normalised values of every number in text, without repeats."""
    seen: list[Decimal] = []
    for mention in find_numbers(text):
        for value in mention.alternatives:
            if value not in seen:
                seen.append(value)
    return seen


def _month_number(name: str) -> int:
    return ("jan feb mar apr may jun jul aug sep oct nov dec".split()).index(name[:3].lower()) + 1


def _full_year(token: str) -> int:
    return int(token) if len(token) == 4 else 2000 + int(token)


def find_dates(text: str) -> list[tuple[int, int, tuple[int, int, int]]]:
    """Return (start, end, (year, month, day)) for every calendar date in text."""
    found: list[tuple[int, int, tuple[int, int, int]]] = []
    for match in _DAY_MONTH_YEAR.finditer(text):
        day, month, year = match.groups()
        found.append((*match.span(), (int(year), _month_number(month), int(day))))
    for match in _MONTH_DAY_YEAR.finditer(text):
        month, day, year = match.groups()
        found.append((*match.span(), (int(year), _month_number(month), int(day))))
    for match in _ISO_DATE.finditer(text):
        year, month, day = match.groups()
        found.append((*match.span(), (int(year), int(month), int(day))))
    for match in _NUMERIC_DATE.finditer(text):
        day, _, month, year = match.groups()
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            found.append((*match.span(), (_full_year(year), int(month), int(day))))
    found.sort()
    return found


def names_a_period(text: str) -> bool:
    """Return True when text contains a fiscal-year, year, quarter or "as at/of" token."""
    return _PERIOD.search(text) is not None


def _is_period_token(mention: NumberMention, statement: str) -> bool:
    return any(
        match.start() <= mention.start and mention.end <= match.end()
        for match in _PERIOD.finditer(statement)
    )


def _has_period_nearby(mention: NumberMention, cited_text: str) -> bool:
    window = cited_text[max(0, mention.start - PERIOD_WINDOW) : mention.end + PERIOD_WINDOW]
    return names_a_period(window)


def _inside(mention: NumberMention, spans: list[tuple[int, int, tuple[int, int, int]]]) -> bool:
    return any(start <= mention.start < end for start, end, _ in spans)


def _fiscal_requirements(mentions: list[NumberMention]) -> list[list[NumberMention]]:
    """Group the mentions of one FY token (both years of FY2025-26) into one requirement."""
    groups: list[list[NumberMention]] = []
    for mention in mentions:
        if (
            groups
            and mention.fiscal
            and groups[-1][-1].fiscal
            and (groups[-1][-1].start == mention.start)
        ):
            groups[-1].append(mention)
        else:
            groups.append([mention])
    return groups


def statement_numbers_supported(
    statement: str, cited_text: str, *, require_period_adjacency: bool = False
) -> tuple[bool, list[str]]:
    """Check each statement number occurs in the cited text; return (ok, unmatched numbers)."""
    cited = find_numbers(cited_text)
    cited_dates = {date for *_, date in find_dates(cited_text)}
    statement_dates = find_dates(statement)
    check_period = require_period_adjacency and names_a_period(statement)
    missing: list[str] = []
    for start, end, date in statement_dates:
        if date not in cited_dates:
            missing.append(statement[start:end])
    plain = [m for m in find_numbers(statement) if not _inside(m, statement_dates)]
    for group in _fiscal_requirements(plain):
        mention = group[0]
        wanted = {abs(value) for member in group for value in member.alternatives}
        hits = [m for m in cited if any(abs(v) in wanted for v in m.alternatives)]
        if check_period and hits and not _is_period_token(mention, statement):
            hits = [m for m in hits if _has_period_nearby(m, cited_text)]
        if not hits:
            missing.append(mention.text)
    return not missing, missing
