"""Fetch, on demand, the facts a bank score input needs but the extractor never produced.

After binding (and the deterministic derivation fallback), every fact-backed slot that is still
unbound is searched for in the documents. A plain slot is one search target; a derived slot
(`derive_from`) is searched whether or not the binder bound it (a partly bound slot, such as a
net debt computed without its lease liabilities, is exactly the case to repair): one target per
statement line item of every component for which no fact OF THE REPORTING BASIS states a
current-year figure (for example "interest paid" and "scheduled principal repayments" of
`debt_service`, or "current lease liabilities" and "non-current lease liabilities" of `net_debt`).
Every target carries the basis word (consolidated or standalone): it opens the queries and the
model prompt, and hits from pages of the other basis are ranked after those of the wanted basis
(`page_bases`), so a standalone cash-flow page no longer outranks the consolidated one. A plain
slot read from one statement row (`components.SLOT_ROWS`) is searched under the row the policy
names ("finance cost" for interest expense) and with its statement in the query ("statement of
profit and loss"), not under the slot's own name, which may be a narrower row.

For each target: up to `MAX_QUERIES` queries are built from the cash-flow statement line wordings
of the component (`CASH_FLOW_LINES`: "Repayment of Long Term Borrowings", "Finance Cost" ...), the
component phrase with the fiscal year of the pack's latest money facts, the slot description, and
the clause of the policy definition that contains the component phrase verbatim; vector search
(k=12, once preferring document kinds financial_statements and annual_report and once over all
kinds) gives the hits, which are deduplicated and ordered by reciprocal-rank fusion over all
queries; at most `HITS_PER_COMPONENT` hits are read, one `policy.slot_extract` LLM call each,
until one returns
`found` with a quote that is verbatim in the chunk. Found results become `NotebookEntry`
objects (`added_by="slot_search"`) that go through `verify_entries(check_relevance=False)` for
the normal number match and entailment; survivors that do not duplicate an existing fact are
appended to `verified_facts.json` with the next F ids. A run makes at most `DEFAULT_BUDGET`
extract calls in total (`BUSYBEE_SLOT_SEARCH_BUDGET`, 0 disables the step). Everything (queries,
hits tried with outcomes, entries, verification results, call counts) goes to `slot_search.json`
and a summary line to the LLM audit log. `rebind_slots` then re-runs the binder for the
affected slots only and merges the result into the earlier binding; a slot the rebind leaves
unbound keeps an earlier binding (a subtotal computed in code after the first bind).

Targets that block a score (an unbound plain slot, an unbound derived slot) come first, then
those that only lift a caution (a missing component of a bound derived slot), each group taken
round-robin over slots (`interleaved`), so one slot with many missing line items cannot spend
the whole budget before another slot's first component is searched. Among the caution targets
the components of `components.CAUTION_FIRST` (cash taxes paid, the one row CFADS lacks) go
first. A cash-flow-only row (`components.CASH_FLOW_ROW_ITEMS`: income tax paid) is read from the
cash flow statement: its queries name operating activities, and the chunks of a cash flow
statement page holding a row that opens with one of its wordings ("Income taxes paid (net of
refunds)", "Direct taxes paid (net)", "Taxes paid", "Income tax paid") are tried before the
vector hits (`row_hits`), other cash flow pages before the remaining hits; a tax movement note
("Add: Taxes paid (net)") is not such a row. An unbound balance-sheet
subtotal slot (current assets) is also searched through the printed totals it equals
(`subtotals.subtotal_search_rows`: total assets, total non-current assets), and the extract
prompt names an unlabelled subtotal row as the section total. A hit
on a page whose heading names the other basis ("Notes (Standalone)") is skipped. The figure's
unit is never the model's word alone: `chunk_unit` (`verify/table_units.py`, shared with the
verify stage) reads the table or page header ("All amounts in INR lakhs", "₹ in lakhs",
"(H in lakhs)" with a garbled rupee sign, "(Rs. lakh)", "Rs. Mn", "(INR million)", "₹ '000")
from the chunk's table prefix, the passage above the row, or an earlier chunk of the same
page, and the statement is rewritten so the printed figure carries it ("INR 1,234.56 lakh",
an outflow printed in brackets as "an outflow of INR 987.65 lakh"); scaling then converts it
to crore like every other fact.
Before any model reading, an unbound subtotal slot (current assets, current liabilities) is
read in code from the balance-sheet pages of the basis (`section_totals`): the section's total
row, labelled or not, checked against the sum of the section's rows, or that sum when the section
prints no total; such a slot is then not searched by the model at all. The model prompt does not
show the slot's scoring unit ("INR crore x 100"), which the model used to copy into the
statement; a unit word or scale left next to the figure ("INR crore 3,395", "3,27,177 INR crore x
100") is replaced together with the figure by the header unit.
When no hit yields a figure, a row of the wanted line item printed as a dash or "Nil" under the
target-year column is taken as a stated zero (`nil_rows`), cited to its chunk without an extract
call.
"""

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from busybee.index import VectorStore, batch_search, embedder_from_env
from busybee.index.embedder.protocol import Embedder
from busybee.ingest.chunker import chunk_with_prefix
from busybee.llm import Message, Provider, Role, StructuredOutputError, complete_as
from busybee.llm.audit_log import record
from busybee.policy.bank_inputs import read_all_facts
from busybee.policy.bind_inputs import (
    BindingResult,
    bind_inputs,
    latest_money_year,
    line_item_stated,
    unresolved_components,
)
from busybee.policy.components import (
    CASH_FLOW_ROW_ITEMS,
    CAUTION_FIRST,
    SEARCH_LINE_ITEMS,
    normalise_component,
    out_of_basis_reason,
    reporting_basis,
    search_items,
    search_phrase,
    slot_rows,
)
from busybee.policy.nil_rows import is_nil_entry, nil_fact, nil_row_entry
from busybee.policy.policy_sections import PolicySection
from busybee.policy.section_totals import section_total_facts
from busybee.policy.subtotals import subtotal_search_rows
from busybee.schema.documents import Chunk, DocumentKind
from busybee.schema.facts import Citation, FactCategory, FactScope, NotebookEntry, VerifiedFact
from busybee.schema.io import write_json_atomic, write_models_atomic
from busybee.schema.policy import InputSlot, ScoreSpec
from busybee.verify.assign_ids import assign_fact_ids
from busybee.verify.entailment import locate_quote
from busybee.verify.number_match import find_numbers
from busybee.verify.table_units import chunk_unit
from busybee.verify.table_units import last_unit as _last_unit
from busybee.verify.verify_entries import VerifyContext, verify_entries

EXTRACT_TASK = "policy.slot_extract"
ADDED_BY = "slot_search"
LOG_FILE = "slot_search.json"
BUDGET_ENV = "BUSYBEE_SLOT_SEARCH_BUDGET"
DEFAULT_BUDGET = 60
HITS_PER_COMPONENT = 6
SEARCH_K = 12
MAX_QUERIES = 5
_RRF_OFFSET = 60
_CLAUSE_TAIL = 90
PREFERRED_KINDS = (DocumentKind.financial_statements, DocumentKind.annual_report)
_IMPORTANCE = 4
_DEFINITION_CHARS = 200
_FLOW_WORDS = re.compile(r"\b(paid|(?:re)?payments?|proceeds|taxes)\b", re.IGNORECASE)
CASH_FLOW_LINES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("interest",),
        ("Interest paid", "Finance costs paid"),
    ),
    (
        ("lease",),
        ("Payment of lease liabilities", "Principal repayment of lease liabilities"),
    ),
    (
        ("principal", "repayment"),
        (
            "Repayment of long-term borrowings",
            "Repayment of non-current borrowings",
            "Repayment of term loans",
            "Repayment of borrowings",
        ),
    ),
    (
        ("tax",),
        (
            "Income taxes paid (net of refunds)",
            "Direct taxes paid (net)",
            "Taxes paid",
            "Income tax paid",
        ),
    ),
    (("dividend",), ("Dividend Paid",)),
)
OPERATING_KEYS = ("tax",)
_ACTIVITY = {
    True: "cash flow from operating activities",
    False: "cash flow from financing activities",
}
_CASH_FLOW_PAGE = re.compile(
    r"statement of cash flows?|cash flow statement|cash flows? (?:from|used in) (?:operating|"
    r"investing|financing)|cash generated from operations",
    re.IGNORECASE,
)
_CATEGORY_WORDS = (
    (FactCategory.cash_flow, ("cash", "cfads", "paid", "tax")),
    (FactCategory.revenue, ("revenue", "turnover", "sales")),
    (FactCategory.profitability, ("ebitda", "profit", "margin")),
    (FactCategory.liquidity, ("current", "liquid")),
    (FactCategory.debt_leverage, ("debt", "borrowing", "interest", "repay", "equity", "worth")),
)

_SYSTEM = (
    "You read ONE passage from a borrower's financial documents and extract a single figure "
    "for a credit score input. The passage may be a table: read its header (units such as "
    "INR lakhs or crore, and the column for each year) and find the ROW whose label matches "
    "the wanted component, allowing the usual statement wording (for example 'Repayment of "
    "Long Term Borrowings' is the principal repayment of borrowings; 'Interest paid' or "
    "'Finance Cost' in the cash flow statement is interest paid). Figures in brackets, such as "
    "(1,234.56), are outflows; they are the figure asked for, so report the number as printed. "
    "Use the column of the latest audited year and prefer consolidated figures when both are "
    "shown. If such a row exists, answer found=true with: statement, one self-contained "
    "sentence that starts with the quantity name as given, names the company's period as "
    "dated in the header (for example 'the year ended March 31, 2026' or 'as at March 31, "
    "2026') and writes the figure exactly as printed with the table's unit (INR "
    "crore, INR lakh or INR million); value, the printed number; unit; period; and quote, a "
    "span copied VERBATIM from the passage that contains the row label and the number. "
    "A balance sheet may print a section subtotal as a row of figures with no label, right "
    "after the section's rows (the row after the last current-asset row is total current "
    "assets): such a row is that subtotal; quote the row itself. "
    'Otherwise answer {"found": false}. Never compute, convert, sum or guess; never use a '
    "figure of another period or another quantity."
)


_STATEMENT_HEADING = re.compile(
    r"^\s*(?:notes to (?:the )?)?(consolidated|standalone|stand[- ]alone)?\s*"
    r"(?:balance sheet|statement of (?:profit|assets|cash)|cash flow)",
    re.IGNORECASE | re.MULTILINE,
)
_NAMES_CONSOLIDATED = re.compile(
    r"^\s*(?:notes to (?:the )?)?consolidated\s+(?:balance sheet|statement|cash flow|financial)"
    r"|^\s*notes?\b[^\n]{0,40}\(\s*consolidated\s*\)",
    re.IGNORECASE | re.MULTILINE,
)
_NAMES_STANDALONE = re.compile(
    r"^\s*notes?\b[^\n]{0,40}\(\s*stand[- ]?alone\s*\)", re.IGNORECASE | re.MULTILINE
)
_UNIT_WORD = (
    r"(?:lakhs?|lacs?|crores?|cr\b|millions?|mn\b|billions?|bn\b|thousands?)"
    r"(?:\s*[x×]\s*\d+\b)?"
)
_FIGURE_UNIT = re.compile(rf"\s*(?:(?:INR|Rs\.?|₹)\s*)?{_UNIT_WORD}", re.IGNORECASE)
_FIGURE_MARK = re.compile(rf"(?:(?:INR|Rs\.?|₹)\s*(?:{_UNIT_WORD}\s+)?)?$", re.IGNORECASE)


class SlotExtract(BaseModel):
    """The model's answer for one chunk: nothing found, or the figure with a verbatim quote."""

    found: bool = False
    statement: str = ""
    value: str = ""
    unit: str = ""
    period: str = ""
    quote: str = ""

    @field_validator("statement", "value", "unit", "period", "quote", mode="before")
    @classmethod
    def _text(cls, raw: object) -> str:
        return "" if raw is None else str(raw)


@dataclass(frozen=True)
class Target:
    """One thing to look for: a slot, or one component of a derived slot."""

    slot: InputSlot
    score_ids: tuple[str, ...]
    phrase: str
    component: bool
    basis: str = ""


@dataclass
class SearchRecord:
    """Everything that happened for one target, as written to `slot_search.json`."""

    slot: str
    score_ids: list[str]
    component: str
    queries: list[str] = field(default_factory=list)
    hits: list[dict[str, Any]] = field(default_factory=list)
    entry_id: str = ""
    outcome: str = "not_found"
    fact_id: str = ""
    note: str = ""


@dataclass
class SlotSearchResult:
    """What the step added: the new facts, the slots they serve, the log, the calls spent."""

    added: list[VerifiedFact] = field(default_factory=list)
    slots: set[str] = field(default_factory=set)
    calls: int = 0
    records: list[SearchRecord] = field(default_factory=list)


def budget_from_env() -> int:
    """The per-run extract-call budget from BUSYBEE_SLOT_SEARCH_BUDGET (default 24)."""
    raw = os.environ.get(BUDGET_ENV, "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_BUDGET


def _is_searchable(slot: InputSlot) -> bool:
    return not slot.mapping and slot.judge is None and not slot.run_parameter


def _missing_items(
    slot: InputSlot, facts: list[VerifiedFact], basis: FactScope
) -> list[tuple[str, str]]:
    """(component, line item) pairs no fact of the basis states for the latest year."""
    of_basis = [fact for fact in facts if out_of_basis_reason(fact, basis) is None]
    loose = set(unresolved_components(slot, of_basis))
    items: list[tuple[str, str]] = []
    for hint in slot.derive_from:
        if normalise_component(hint) in SEARCH_LINE_ITEMS:
            items += [
                (hint, item)
                for item in search_items(hint)
                if not line_item_stated(item, hint, facts, basis)
            ]
        elif hint in loose:
            items.append((hint, hint.replace("_", " ")))
    return items


def interleaved(targets: list[Target]) -> list[Target]:
    """Round-robin over slots: every slot's first target, then every slot's second, and so on."""
    queues: dict[str, list[Target]] = {}
    for target in targets:
        queues.setdefault(target.slot.slot, []).append(target)
    ordered: list[Target] = []
    depth = 0
    while len(ordered) < len(targets):
        ordered += [queue[depth] for queue in queues.values() if depth < len(queue)]
        depth += 1
    return ordered


def search_targets(
    specs: list[ScoreSpec],
    binding: BindingResult,
    facts: list[VerifiedFact],
    basis: FactScope | None = None,
) -> list[Target]:
    """Targets for unbound plain slots and for the missing components of every derived slot."""
    basis = basis or reporting_basis(facts)
    word = basis.value
    owners: dict[str, list[str]] = {}
    slots: dict[str, InputSlot] = {}
    for spec in specs:
        for slot in spec.inputs:
            if not _is_searchable(slot):
                continue
            unbound = (spec.score_id, slot.slot) in binding.unbound
            if unbound or slot.derive_from:
                slots.setdefault(slot.slot, slot)
                owners.setdefault(slot.slot, []).append(spec.score_id)
    blocking: list[Target] = []
    first: list[Target] = []
    cautions: list[Target] = []
    for name, slot in slots.items():
        ids = tuple(owners[name])
        unbound = any((score, name) in binding.unbound for score in ids)
        if slot.derive_from:
            for hint, item in _missing_items(slot, facts, basis):
                early = normalise_component(hint) in CAUTION_FIRST
                queue = blocking if unbound else first if early else cautions
                queue.append(Target(slot, ids, item, True, word))
        elif unbound:
            blocking.append(Target(slot, ids, search_phrase(slot), False, word))
            blocking += [Target(slot, ids, row, True, word) for row in subtotal_search_rows(slot)]
    return [*interleaved(blocking), *interleaved(first), *interleaved(cautions)]


def cash_flow_wordings(phrase: str) -> list[str]:
    """Cash flow statement line wordings for a flow component such as 'interest paid'."""
    if not _FLOW_WORDS.search(phrase):
        return []
    lowered = phrase.casefold()
    return [
        line
        for keys, lines in CASH_FLOW_LINES
        if any(key in lowered for key in keys)
        for line in lines
    ]


def definition_clause(definition: str, phrase: str) -> str:
    """The stretch of the policy definition starting at the component phrase, verbatim."""
    start = definition.casefold().find(phrase.casefold())
    return "" if start < 0 else definition[start : start + len(phrase) + _CLAUSE_TAIL]


def build_queries(target: Target, year: int) -> list[str]:
    """Up to MAX_QUERIES queries: line wordings, phrase and year, definition clause, description."""
    slot, phrase = target.slot, target.phrase
    when = f"FY{year}" if year else ""
    flow = bool(_FLOW_WORDS.search(phrase))
    rows = slot_rows(slot)
    lead = f"{phrase} cash flow statement" if flow else f"{phrase} balance sheet"
    if rows is not None and not flow:
        lead = f"{phrase} statement of {rows[0]}"
    elif not flow and not target.basis:
        lead = phrase
    activity = _ACTIVITY[any(key in phrase.casefold() for key in OPERATING_KEYS)]
    wordings = [
        f"{target.basis} {line} {activity} {when}".strip() for line in cash_flow_wordings(phrase)
    ]
    clause = definition_clause(slot.definition, phrase)
    candidates = [
        *wordings[:2],
        f"{target.basis} {lead} {when}".strip(),
        clause or (f"{phrase} {slot.definition[:_DEFINITION_CHARS]}" if slot.definition else ""),
        f"{phrase} {slot.description}",
    ]
    queries: list[str] = []
    for text in candidates:
        cleaned = " ".join(text.split())
        if cleaned and cleaned not in queries:
            queries.append(cleaned)
    return queries[:MAX_QUERIES]


async def _ranked_chunks(
    store: VectorStore, embedder: Embedder, queries: list[str]
) -> list[tuple[Chunk, float]]:
    """Distinct hits of all queries, with and without the kind preference, best fused rank first."""
    fused: dict[str, float] = {}
    best: dict[str, tuple[Chunk, float]] = {}
    for kinds in (PREFERRED_KINDS, None):
        lists = await batch_search(store, embedder, queries, k=SEARCH_K, doc_kinds=kinds)
        for hits in lists:
            for rank, hit in enumerate(hits):
                cid = hit.chunk.chunk_id
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_OFFSET + rank)
                if cid not in best or hit.score > best[cid][1]:
                    best[cid] = (hit.chunk, hit.score)
    return [best[cid] for cid in sorted(fused, key=lambda cid: -fused[cid])]


def page_bases(chunks: list[Chunk]) -> dict[tuple[str, int], str]:
    """For each (doc, page), 'consolidated' or 'standalone' when a statement heading says so."""
    pages: dict[tuple[str, int], str] = {}
    named: set[tuple[str, int]] = set()
    for chunk in chunks:
        key = (chunk.doc_id, chunk.page_no)
        if _NAMES_CONSOLIDATED.search(chunk.text):
            pages[key] = "consolidated"
            named.add(key)
        elif _NAMES_STANDALONE.search(chunk.text) and key not in named:
            pages[key] = "standalone"
            named.add(key)
        elif key not in pages and _STATEMENT_HEADING.search(chunk.text):
            pages[key] = "standalone"
    return pages


def with_unit(statement: str, value: str, unit: str) -> str:
    """Rewrite the printed figure in the statement as 'INR <figure> <unit>' (outflows named)."""
    figure = value.strip()
    digits = figure.strip("()").lstrip("-−").strip()
    if not unit or not re.fullmatch(r"[\d,]*\d(?:\.\d+)?", digits):
        return statement
    outflow = figure.startswith(("(", "-", "−"))
    loose = ",?".join(re.escape(char) for char in digits.replace(",", ""))
    for match in re.finditer(rf"(?<![\d,.])\(?[-−]?({loose})\)?(?![\d])", statement):
        start, end = match.span()
        printed = match.group(1)
        mark = _FIGURE_MARK.search(statement[:start])
        start = mark.start() if mark and mark.group(0) else start
        tail = _FIGURE_UNIT.match(statement, end)
        end = tail.end() if tail else end
        words = f"{'an outflow of ' if outflow else ''}INR {printed} {unit}"
        return f"{statement[:start]}{words}{statement[end:]}"
    return statement


def cash_flow_pages(chunks: list[Chunk]) -> set[tuple[str, int]]:
    """The (doc, page) pairs of which some chunk reads as a cash flow statement."""
    return {(c.doc_id, c.page_no) for c in chunks if _CASH_FLOW_PAGE.search(c.text)}


def _row_label_pattern(wording: str) -> re.Pattern[str]:
    words = re.findall(r"[a-z]+", wording.split("(")[0].lower())
    return re.compile(r"^\W*" + r"\W+".join(words) + r"\b", re.IGNORECASE | re.MULTILINE)


def row_hits(target: Target, chunks: list[Chunk]) -> list[tuple[Chunk, float]]:
    """Chunks of a cash flow statement page with a row that opens with the item's wording."""
    if normalise_component(target.phrase) not in CASH_FLOW_ROW_ITEMS:
        return []
    patterns = [_row_label_pattern(line) for line in cash_flow_wordings(target.phrase)]
    pages = cash_flow_pages(chunks)
    return [
        (chunk, 1.0)
        for chunk in chunks
        if (chunk.doc_id, chunk.page_no) in pages
        and any(pattern.search(chunk.text) for pattern in patterns)
    ]


def _cash_flow_first(
    target: Target, ranked: list[tuple[Chunk, float]], chunks: list[Chunk]
) -> list[tuple[Chunk, float]]:
    """For a cash-flow-only item: its statement rows, then other cash flow pages, then the rest."""
    if normalise_component(target.phrase) not in CASH_FLOW_ROW_ITEMS:
        return ranked
    pages = cash_flow_pages(chunks)
    rows = row_hits(target, chunks)
    seen = {chunk.chunk_id for chunk, _ in rows}
    rest = [item for item in ranked if item[0].chunk_id not in seen]
    return [*rows, *sorted(rest, key=lambda item: (item[0].doc_id, item[0].page_no) not in pages)]


def _basis_first(
    ranked: list[tuple[Chunk, float]], bases: dict[tuple[str, int], str], basis: str
) -> list[tuple[Chunk, float]]:
    """Stable reorder: pages of the wanted basis, then pages without a basis, then the other."""

    def tier(item: tuple[Chunk, float]) -> int:
        found = bases.get((item[0].doc_id, item[0].page_no))
        return 1 if found is None else 0 if found == basis else 2

    return sorted(ranked, key=tier) if basis else ranked


def _messages(target: Target, chunk: Chunk, year: int, page_basis: str = "") -> list[Message]:
    slot = target.slot
    lines = [f"Slot: {slot.slot}: {slot.description}"]
    if slot.definition:
        lines.append(f"Definition: {slot.definition}")
    lines.append(f"Component: {target.phrase}")
    if target.basis:
        seen = f"; this page is headed {page_basis}" if page_basis else ""
        lines.append(
            f"Basis: {target.basis} statements only. Ignore figures of the other basis{seen}."
        )
    lines.append(f"Period: latest audited year{f' (FY{year})' if year else ''}")
    wordings = cash_flow_wordings(target.phrase)
    if wordings:
        lines.append(f"Usual statement wording of this row: {'; '.join(wordings)}")
    if chunk.prefix:
        lines.append(f"Table header: {chunk.prefix}")
    lines.append(f"Passage [{chunk.chunk_id}]:\n{chunk.text}")
    return [
        Message(role=Role.system, content=_SYSTEM),
        Message(role=Role.user, content="\n".join(lines)),
    ]


def _category_for(target: Target) -> FactCategory:
    text = f"{target.slot.slot} {target.phrase}".lower()
    for category, words in _CATEGORY_WORDS:
        if any(word in text for word in words):
            return category
    return FactCategory.other


def _with_figure(
    answer: SlotExtract, basis: str, chunk: Chunk, page_chunks: list[Chunk] | None = None
) -> SlotExtract:
    """Give a statement that names only the row its figure, its header unit and the basis word."""
    statement = answer.statement.strip()
    if statement and not find_numbers(statement) and re.search(r"\d", answer.value):
        period = f" for {answer.period}" if answer.period else ""
        statement = f"{statement}{period} was {answer.value.strip()} {answer.unit}".strip()
    unit = chunk_unit(chunk, page_chunks or [], answer.quote) or _last_unit(f"INR {answer.unit}")
    statement = with_unit(statement, answer.value, unit)
    if statement and basis == "consolidated" and basis not in statement.lower():
        statement = f"{basis.capitalize()} {statement[:1].lower()}{statement[1:]}"
    statement = _dated_period(statement, chunk_with_prefix(chunk))
    return answer.model_copy(update={"statement": statement, "unit": unit or answer.unit})


def _dated_period(statement: str, text: str) -> str:
    """Rewrite FY2026 as 'the year ended March 31, 2026' when the passage dates that year end."""

    def spell(match: re.Match[str]) -> str:
        year = match.group(1)
        dated = re.search(rf"31\.03\.{year}|March 31, {year}", text)
        return f"the year ended March 31, {year}" if dated else match.group(0)

    return re.sub(r"\bFY\s?(20\d{2})\b", spell, statement)


def _with_year_source(text: str, quote: str, statement: str) -> str:
    """Widen the quote upward to the nearest line that carries a year the statement names."""
    at = text.find(quote)
    start = at
    for year in {y for y in re.findall(r"20\d{2}", statement) if y not in quote}:
        found = text.rfind(year, 0, at)
        if found >= 0:
            start = min(start, text.rfind("\n", 0, found) + 1)
    return text[start : at + len(quote)] if at >= 0 else quote


def _checked(answer: SlotExtract, chunk: Chunk) -> tuple[str, str]:
    """(outcome, verbatim quote): 'found' only for a numeric statement and a quote in the chunk."""
    if not answer.found:
        return "not_found", ""
    if not answer.statement.strip() or not find_numbers(answer.statement):
        return "statement_without_number", ""
    text = chunk_with_prefix(chunk)
    quote = locate_quote(text, answer.quote)
    return (
        ("found", _with_year_source(text, quote, answer.statement))
        if quote
        else (
            "quote_not_verbatim",
            "",
        )
    )


def _first_nil_entry(
    target: Target,
    year: int,
    ranked: list[tuple[Chunk, float]],
    chunks: list[Chunk],
    bases: dict[tuple[str, int], str],
    entry_id: str,
) -> tuple[NotebookEntry, str] | None:
    """The first hit with a dash or Nil row for the target, as (entry, chunk id); no LLM call."""
    for chunk, _ in ranked:
        page_basis = bases.get((chunk.doc_id, chunk.page_no), "")
        if target.basis and page_basis and page_basis != target.basis:
            continue
        page = [c for c in chunks if (c.doc_id, c.page_no) == (chunk.doc_id, chunk.page_no)]
        entry = nil_row_entry(
            chunk,
            target.phrase,
            year,
            chunk_unit(chunk, page),
            target.basis,
            entry_id,
            _category_for(target),
            _IMPORTANCE,
            ADDED_BY,
        )
        if entry is not None:
            return entry, chunk.chunk_id
    return None


def _with_nil(
    log: SearchRecord, nil: tuple[NotebookEntry, str] | None, used: int
) -> tuple[SearchRecord, NotebookEntry | None, int]:
    """Fall back to the nil row when no model reading found a figure."""
    if nil is None:
        return log, None, used
    entry, chunk_id = nil
    log.entry_id, log.outcome, log.note = entry.entry_id, "found", f"nil row in {chunk_id}"
    return log, entry, used


async def _search_target(
    target: Target,
    year: int,
    store: VectorStore,
    embedder: Embedder,
    provider: Provider,
    calls_left: int,
    entry_id: str,
) -> tuple[SearchRecord, NotebookEntry | None, int]:
    """Read up to four hits for one target; return the log, an entry if found, calls used."""
    log = SearchRecord(target.slot.slot, list(target.score_ids), target.phrase)
    log.queries = build_queries(target, year)
    ranked = await _ranked_chunks(store, embedder, log.queries)
    chunks = list(store.chunks_by_id().values())
    bases = page_bases(chunks)
    ranked = _basis_first(_cash_flow_first(target, ranked, chunks), bases, target.basis)
    used = 0
    nil = _first_nil_entry(target, year, ranked[:HITS_PER_COMPONENT], chunks, bases, entry_id)
    for chunk, score in ranked[:HITS_PER_COMPONENT]:
        if used >= calls_left:
            log.outcome, log.note = "budget_exhausted", "run budget of extract calls spent"
            return _with_nil(log, nil, used)
        hit = {"chunk_id": chunk.chunk_id, "score": round(score, 4), "outcome": ""}
        log.hits.append(hit)
        page_basis = bases.get((chunk.doc_id, chunk.page_no), "")
        if target.basis and page_basis and page_basis != target.basis:
            hit["outcome"] = "other_basis"
            continue
        used += 1
        try:
            answer = await complete_as(
                provider,
                _messages(target, chunk, year, page_basis),
                SlotExtract,
                task=EXTRACT_TASK,
            )
        except StructuredOutputError:
            hit["outcome"] = "invalid_reply"
            continue
        page = [c for c in chunks if (c.doc_id, c.page_no) == (chunk.doc_id, chunk.page_no)]
        answer = _with_figure(answer, target.basis, chunk, page)
        hit["outcome"], quote = _checked(answer, chunk)
        if hit["outcome"] != "found":
            continue
        log.entry_id, log.outcome = entry_id, "found"
        entry = NotebookEntry(
            entry_id=entry_id,
            statement=answer.statement.strip(),
            citations=[
                Citation(
                    chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no, quote=quote
                )
            ],
            category=_category_for(target),
            doc_id=chunk.doc_id,
            importance=_IMPORTANCE,
            added_by=ADDED_BY,
        )
        return log, entry, used
    if not ranked:
        log.note = "no passages retrieved"
    return _with_nil(log, nil, used)


def _squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def _is_duplicate(fact: VerifiedFact, existing: list[VerifiedFact]) -> VerifiedFact | None:
    chunks = {c.chunk_id for c in fact.citations}
    values = {n.value for n in fact.numbers}
    for other in existing:
        same_text = _squash(other.statement) == _squash(fact.statement)
        same_source = (
            bool(values)
            and values == {n.value for n in other.numbers}
            and bool(chunks & {c.chunk_id for c in other.citations})
        )
        if same_text or same_source:
            return other
    return None


def _next_number(facts: list[VerifiedFact]) -> int:
    numbers = [int(f.fact_id[1:]) for f in facts if f.fact_id[1:].isdigit()]
    return max(numbers, default=0) + 1


def _write_log(workspace: Path, result: SlotSearchResult, budget: int, note: str = "") -> None:
    write_json_atomic(
        workspace / LOG_FILE,
        {
            "note": note,
            "budget": {
                "per_component": HITS_PER_COMPONENT,
                "per_run": budget,
                "extract_calls": result.calls,
            },
            "added_fact_ids": [fact.fact_id for fact in result.added],
            "searches": [vars(item) for item in result.records],
        },
    )


async def fill_unbound_slots(
    workspace_dir: Path,
    provider: Provider,
    specs: list[ScoreSpec],
    facts: list[VerifiedFact],
    binding: BindingResult,
    *,
    budget: int | None = None,
    store: VectorStore | None = None,
    embedder: Embedder | None = None,
) -> SlotSearchResult:
    """Search the documents for every unbound slot or component and append verified facts."""
    workspace = Path(workspace_dir)
    budget = budget_from_env() if budget is None else budget
    result = SlotSearchResult()
    basis = reporting_basis(facts)
    targets = search_targets(specs, binding, facts, basis) if budget > 0 else []
    index_dir = workspace / "index"
    if store is None and (index_dir / "vectors.npy").exists():
        store = VectorStore.load(index_dir)
    if not targets or store is None:
        note = "disabled" if budget <= 0 else "nothing unbound" if not targets else "no index"
        _write_log(workspace, result, budget, note)
        return result
    embedder = embedder or embedder_from_env()
    year = latest_money_year(facts)
    entries: list[NotebookEntry] = []
    found_by_phrase: dict[str, SearchRecord] = {}
    every_chunk = list(store.chunks_by_id().values())
    read = section_total_facts(specs, binding, every_chunk, page_bases(every_chunk), year)
    read = {name: fact for name, fact in read.items() if any(t.slot.slot == name for t in targets)}
    for name, fact in read.items():
        owner = next(target for target in targets if target.slot.slot == name)
        result.records.append(
            SearchRecord(
                name,
                list(owner.score_ids),
                owner.phrase,
                entry_id=fact.source_entry_id or "",
                outcome="found",
                note=f"section total read in code from {fact.citations[0].chunk_id}",
            )
        )
    targets = [target for target in targets if target.slot.slot not in read]
    for target in targets:
        key = target.phrase.casefold()
        if target.component and key in found_by_phrase:
            earlier = found_by_phrase[key]
            result.records.append(
                SearchRecord(
                    target.slot.slot,
                    list(target.score_ids),
                    target.phrase,
                    outcome=earlier.outcome,
                    entry_id=earlier.entry_id,
                    note="shares the search made for another slot",
                )
            )
            continue
        log, entry, used = await _search_target(
            target,
            year,
            store,
            embedder,
            provider,
            budget - result.calls,
            f"SLOT:E{len(entries) + 1:03d}",
        )
        result.calls += used
        result.records.append(log)
        found_by_phrase[key] = log
        if entry is not None:
            entries.append(entry)
    await _verify_and_append(
        workspace, provider, store, embedder, entries, result, list(read.values())
    )
    _write_log(workspace, result, budget)
    await record(
        {
            "task": f"{EXTRACT_TASK}.summary",
            "extract_calls": result.calls,
            "budget_per_run": budget,
            "budget_per_component": HITS_PER_COMPONENT,
            "targets": len(targets),
            "facts_added": len(result.added),
        }
    )
    return result


async def _verify_and_append(
    workspace: Path,
    provider: Provider,
    store: VectorStore,
    embedder: Embedder,
    entries: list[NotebookEntry],
    result: SlotSearchResult,
    read: list[VerifiedFact] | None = None,
) -> None:
    """Verify the entries, drop duplicates of existing facts, number and append the survivors."""
    if not entries and not read:
        return
    existing = read_all_facts(workspace)
    nil_entries = [entry for entry in entries if is_nil_entry(entry)]
    entries = [entry for entry in entries if not is_nil_entry(entry)]
    ctx = VerifyContext(
        provider=provider, chunks_by_id=store.chunks_by_id(), store=store, embedder=embedder
    )
    verified, dropped = (
        await verify_entries(entries, ctx, check_relevance=False) if entries else ([], [])
    )
    verified = [*verified, *(nil_fact(entry) for entry in nil_entries), *(read or [])]
    by_entry = {item.entry.entry_id: item.reason for item in dropped}
    fresh: list[VerifiedFact] = []
    for fact in verified:
        twin = _is_duplicate(fact, [*existing, *fresh])
        if twin is None:
            fresh.append(fact)
        for item in result.records:
            if item.entry_id == fact.source_entry_id:
                item.outcome = "verified" if twin is None else "duplicate"
                item.note = f"duplicate of {twin.fact_id}" if twin else item.note
    for item in result.records:
        if item.entry_id in by_entry:
            item.outcome, item.note = "dropped", by_entry[item.entry_id]
    numbered = assign_fact_ids(fresh, start=_next_number(existing))
    for fact in numbered:
        for item in result.records:
            if item.entry_id == fact.source_entry_id:
                item.fact_id = fact.fact_id
    if numbered:
        write_models_atomic(workspace / "verified_facts.json", [*existing, *numbered])
    result.added = numbered
    result.slots = {item.slot for item in result.records if item.fact_id}


async def rebind_slots(
    provider: Provider,
    specs: list[ScoreSpec],
    facts: list[VerifiedFact],
    binding: BindingResult,
    slots: set[str],
    sections: list[PolicySection],
) -> BindingResult:
    """Re-run the binder for the named slots only and merge its answers into `binding`."""
    wanted = set(slots) | {
        slot.slot
        for spec in specs
        for slot in spec.inputs
        if slot.fallback_slot in slots and (spec.score_id, slot.slot) in binding.unbound
    }
    narrowed = [
        spec.model_copy(update={"inputs": [s for s in spec.inputs if s.slot in wanted]})
        for spec in specs
    ]
    narrowed = [spec for spec in narrowed if spec.inputs]
    if not narrowed:
        return binding
    again = await bind_inputs(provider, narrowed, facts, sections)
    merged = copy.deepcopy(binding)
    for spec in narrowed:
        have = {item.slot for item in again.bound.get(spec.score_id, [])}
        kept = [item for item in merged.bound.get(spec.score_id, []) if item.slot not in have]
        merged.bound[spec.score_id] = [*kept, *again.bound.get(spec.score_id, [])]
        for slot in spec.inputs:
            key = (spec.score_id, slot.slot)
            if slot.slot in have:
                merged.unbound.pop(key, None)
            elif key in again.unbound and not any(item.slot == slot.slot for item in kept):
                merged.unbound[key] = again.unbound[key]
    merged.rejected = [*binding.rejected, *again.rejected]
    return merged
