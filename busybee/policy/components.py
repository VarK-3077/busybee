"""Plain-language component definitions for derived slots, and the code checks on a binding.

A derived slot (net debt, CFADS, debt service, tangible net worth) lists its components in
`derive_from`. `component_lines` renders the meaning of each component for the bind prompt so
the model sees exactly what the policy means by it (liquid investments are current investments
only; lease liabilities are current plus non-current; cash taxes are income tax paid, not the
tax charge). After the model answers, `uncovered_components` says which components it neither
used as a term nor declared missing, and `wrong_section_reason` rejects a term for a
current-only component (liquid investments) whose fact sits under non-current assets or is an
investment in a subsidiary. `reporting_basis` picks the statement basis for every ratio:
consolidated when the documents hold consolidated statements, else standalone.

`LINE_ITEMS` are the statement rows that ADD UP to a component (current plus non-current lease
liabilities; repayment of long-term borrowings plus payment of lease liabilities), and
`ITEM_WORDINGS` the other ways one row is printed ("Repayment of non-current borrowings", "Repayment
of term loans"); `item_wordings` gives a row with its alternatives. `CAUTION_FIRST` are the
components the slot search looks for first among those that only lift a caution (cash taxes paid),
and `CASH_FLOW_ROW_ITEMS` the rows it reads from the cash flow statement only. `outlier_reason` is
the sanity guard on a term: a money figure more than `OUTLIER_RATIO` times larger or smaller than
the same line item on the other basis or in another year (typically a lakh table read as crore) is
reported so the binding carries a caution instead of using it silently. Only INR amounts of the same
line item are compared (a figure labelled for another row, a share count, a percentage, a ratio or a
foreign-currency amount is never a comparator). The comparator must also be like for like: the other
basis in the same year, or the same basis one year apart (a figure six years older in an offer
document may well be 20 times smaller), a balance against a balance and a cash flow against a cash
flow (net proceeds from borrowings is no borrowings balance), and never a change figure ("EBITDA
decreased by INR 501.29 million").

`SUBTOTAL_FORMULAS` gives, for a balance-sheet subtotal slot whose row is often printed without a
label (current assets, current liabilities), the printed totals it equals: total assets less
total non-current assets; total liabilities less non-current liabilities, or total equity and
liabilities less equity less non-current liabilities (`subtotals.py` applies them).

`unsigned_term` says when a derived-slot term enters by its absolute figure, the sign coming only
from the term: its component is a cash-flow component (also when the model names it loosely,
"principal repayments" for scheduled principal repayments), or its fact states an outflow
("paid", "repayment", "an outflow of"), however the figure is written (negative, bracketed).

`SLOT_ROWS` names, for a plain slot the policy defines by one statement row (gross finance cost,
EBITDA), the statement it is read from and its rows in order of preference: the first tier is
the row the definition names, a later tier a stand-in (interest expense for finance cost; profit
before finance cost and depreciation, which includes other income, for EBITDA) that binds with a
proxy caution. `statement_fits` keeps a profit and loss item off cash-flow facts and a cash-flow
item on them (`is_flow_fact`: category cash flow, or a statement that says paid, repayment,
payment, outflow or cash flow). `term_proxy_reason` is the only source of a derived term's proxy
flag: a term is a proxy when its component is not one the slot names, when a cash-flow component
comes from a fact that is not a cash flow (or a balance component from one that is), or when the
fact states neither the component nor any of its rows; the model's own note never sets it.
"""

import re
from collections.abc import Iterable
from decimal import Decimal

from busybee.schema.facts import FactCategory, FactScope, NumericValue, VerifiedFact
from busybee.schema.policy import InputSlot

COMPONENT_MEANINGS = {
    "total borrowings": (
        "all borrowings, short-term plus long-term, including the current maturities of "
        "long-term borrowings; lease liabilities are a separate component"
    ),
    "lease liabilities": (
        "lease liabilities, current plus non-current (add both parts; use one total only "
        "when that is all the documents give)"
    ),
    "cash and bank balances": (
        "cash and cash equivalents plus other bank balances (including bank deposits) "
        "under current assets"
    ),
    "liquid investments": (
        "current investments only: mutual funds, treasury bills and fixed deposits shown "
        "under current assets; never non-current investments or investments in "
        "subsidiaries, associates or joint ventures"
    ),
    "ebitda": "operating profit before depreciation, interest and tax, excluding other income",
    "cash taxes paid": (
        "income tax paid (net of refunds) from the cash-flow statement, not the tax expense "
        "of the profit and loss statement"
    ),
    "interest paid": "interest paid in cash in the year (cash-flow statement), not accrued",
    "scheduled principal repayments": (
        "repayment of long-term borrowings in the year plus the principal part of lease "
        "payments, from the cash-flow statement; not working-capital drawings"
    ),
    "total equity": "shareholders' equity (net worth) at the year end",
    "intangible assets": (
        "goodwill, other intangible assets and intangible assets under development at the year end"
    ),
}
LINE_ITEMS = {
    "total borrowings": ("non-current borrowings", "current borrowings"),
    "lease liabilities": ("non-current lease liabilities", "current lease liabilities"),
    "cash and bank balances": (
        "cash and cash equivalents",
        "bank balances other than cash and cash equivalents",
    ),
    "liquid investments": ("current investments",),
    "cash taxes paid": ("income tax paid",),
    "interest paid": ("interest paid",),
    "scheduled principal repayments": (
        "repayment of long term borrowings",
        "payment of lease liabilities",
    ),
    "intangible assets": (
        "other intangible assets",
        "intangible assets under development",
        "goodwill",
    ),
    "ebitda": ("operating profit before depreciation, interest and tax",),
    "total equity": ("total equity",),
}
ITEM_WORDINGS = {
    "interest paid": ("finance cost paid", "finance costs paid", "finance cost"),
    "repayment of long term borrowings": (
        "repayment of non-current borrowings",
        "repayment of term loans",
        "repayment of long term loans",
        "repayment of borrowings",
        "repayment of secured loans",
    ),
    "payment of lease liabilities": (
        "payment of lease liability",
        "repayment of lease liabilities",
        "principal portion of lease payments",
        "principal payment of lease liabilities",
        "principal repayment of lease liabilities",
        "principal element of lease payments",
    ),
    "income tax paid": ("income taxes paid", "direct taxes paid", "taxes paid"),
}
CAUTION_FIRST = frozenset({"cash taxes paid"})
CASH_FLOW_ROW_ITEMS = frozenset({"income tax paid"})
SEARCH_LINE_ITEMS = frozenset(
    {
        "scheduled principal repayments",
        "lease liabilities",
        "cash and bank balances",
        "liquid investments",
        "cash taxes paid",
        "intangible assets",
    }
)
LINE_ITEM_SOURCE = {
    "cash taxes paid": "cash-flow statement, net of refunds",
    "interest paid": "cash-flow statement",
    "scheduled principal repayments": "cash-flow statement",
    "liquid investments": "current assets only",
    "cash and bank balances": "current assets",
}
CURRENT_ONLY = frozenset({"liquid investments"})
SLOT_ROWS: dict[str, tuple[str, tuple[tuple[str, ...], ...]]] = {
    "interest expense": (
        "profit and loss",
        (
            ("finance cost", "finance cost expensed in profit or loss", "finance charges"),
            ("interest expense", "interest and finance charges"),
        ),
    ),
    "ebitda": (
        "profit and loss",
        (
            ("ebitda", "adjusted ebitda", "operating ebitda", "opbdit", "operating profit before"),
            ("profit before finance cost depreciation", "profit before interest depreciation"),
        ),
    ),
}
_NON_CURRENT_LIABILITIES = ("total non-current liabilities", "non-current liabilities")
SUBTOTAL_FORMULAS: dict[str, tuple[tuple[tuple[int, tuple[str, ...]], ...], ...]] = {
    "current assets": (
        ((1, ("total assets",)), (-1, ("total non-current assets", "non-current assets"))),
    ),
    "current liabilities": (
        ((1, ("total liabilities",)), (-1, _NON_CURRENT_LIABILITIES)),
        (
            (1, ("total equity and liabilities",)),
            (-1, ("total equity",)),
            (-1, _NON_CURRENT_LIABILITIES),
        ),
    ),
}
BALANCE_ITEMS = frozenset(
    {
        "total borrowings",
        "lease liabilities",
        "cash and bank balances",
        "liquid investments",
        "total equity",
        "intangible assets",
    }
)
_FLOW_WORDS = re.compile(r"\b(?:paid|repayments?|payments?|outflows?|cash[- ]flows?)\b", re.I)
_OUTFLOW_WORDS = re.compile(r"\b(?:paid|repaid|repayments?|payments?|outflows?)\b", re.I)
_MIN_CONSOLIDATED_FACTS = 5
_NON_CURRENT = re.compile(
    r"non[- ]?current|investments?\s+in\s+(?:subsidiar|associate|joint)", re.IGNORECASE
)
_FIGURES = re.compile(r"\d")
OUTLIER_RATIO = 20
_YEAR_REACH = 1
_CHANGE_WORDS = re.compile(
    r"\b(?:increase[ds]?|decrease[ds]?|decline[ds]?|grew|growth|change[ds]?|rose|fell|"
    r"higher|lower|up|down)\b",
    re.IGNORECASE,
)
_CRORE_PER = {
    "crore": Decimal(1),
    "crores": Decimal(1),
    "cr": Decimal(1),
    "lakh": Decimal("0.01"),
    "lakhs": Decimal("0.01"),
    "lac": Decimal("0.01"),
    "million": Decimal("0.1"),
    "mn": Decimal("0.1"),
    "billion": Decimal(100),
    "bn": Decimal(100),
    "thousand": Decimal("0.0001"),
    "thousands": Decimal("0.0001"),
}
_YEAR = re.compile(r"(?:19|20)\d{2}")
_BASIS_WORDS = frozenset({"consolidated", "standalone", "total", "the", "of", "and", "other"})
_GENERIC_LABEL_WORDS = frozenset({"value", "amount", "figure", "balance", "as", "at", "for", "in"})
_INR_MARKS = frozenset({"inr", "rs", "rupee", "rupees"})
_FOREIGN_MARKS = frozenset({"usd", "eur", "euro", "gbp", "jpy", "chf", "dollar", "dollars"})
_COUNT_WORDS = frozenset(
    {"share", "shares", "nos", "number", "units", "unit", "count", "percent", "times", "ratio"}
)


def normalise_component(name: str) -> str:
    """Lowercase component name with underscores and punctuation turned into single spaces."""
    return " ".join(re.findall(r"[a-z0-9]+", name.lower()))


def component_lines(slot: InputSlot) -> list[str]:
    """One meaning line per `derive_from` component of the slot, for the bind prompt."""
    return [
        f"    component '{hint}': "
        + COMPONENT_MEANINGS.get(normalise_component(hint), "the figure the name describes")
        for hint in slot.derive_from
    ]


def same_component(left: str, right: str) -> bool:
    """True when two component names are equal after normalising, or one holds the other."""
    a, b = normalise_component(left), normalise_component(right)
    return bool(a and b) and (a == b or a in b or b in a)


def uncovered_components(slot: InputSlot, used: Iterable[str], missing: Iterable[str]) -> list[str]:
    """The slot's components that appear neither among the used term names nor as missing."""
    named = [*used, *missing]
    return [
        hint for hint in slot.derive_from if not any(same_component(hint, name) for name in named)
    ]


def heading_text(fact: VerifiedFact) -> str:
    """The words that say where in the statements a fact sits: section, metric and statement."""
    record = fact.record
    section = getattr(record, "section", None) if record is not None else None
    metric = record.metric if record is not None else ""
    return f"{section or ''} {metric} {fact.statement}"


def wrong_section_reason(component: str, fact: VerifiedFact) -> str | None:
    """Why the fact cannot supply a current-only component (non-current, subsidiary), else None."""
    if normalise_component(component) not in CURRENT_ONLY:
        return None
    found = _NON_CURRENT.search(heading_text(fact))
    if found is None:
        return None
    return (
        f"{fact.fact_id} is under non-current assets or is an investment in a subsidiary "
        f"({found.group(0)!r}); {component} are current investments only"
    )


def reporting_basis(facts: Iterable[VerifiedFact]) -> FactScope:
    """Consolidated when the documents hold consolidated statements, else standalone."""
    consolidated = sum(
        1
        for fact in facts
        if fact.scope is FactScope.consolidated
        and (fact.numbers or _FIGURES.search(fact.statement))
    )
    return (
        FactScope.consolidated if consolidated >= _MIN_CONSOLIDATED_FACTS else FactScope.standalone
    )


def out_of_basis_reason(fact: VerifiedFact, basis: FactScope) -> str | None:
    """Why a fact of the other basis may not feed a rule, else None (unscoped facts are fine)."""
    if fact.scope is None or fact.scope is basis:
        return None
    return f"{fact.fact_id} is {fact.scope.value} but this run uses {basis.value} figures"


def line_items(component: str) -> tuple[str, ...]:
    """The plain statement line items that make up a component (the component itself if unknown)."""
    return LINE_ITEMS.get(normalise_component(component), (component.replace("_", " "),))


def search_items(component: str) -> tuple[str, ...]:
    """The line items the slot search looks up one by one: each is a single row of a statement."""
    name = normalise_component(component)
    return line_items(component) if name in SEARCH_LINE_ITEMS else (component.replace("_", " "),)


def item_wordings(item: str) -> tuple[str, ...]:
    """A statement row and the other wordings it is printed with, the row itself first."""
    name = normalise_component(item)
    return (item, *ITEM_WORDINGS.get(name, ()))


def _item_words(component: str) -> set[str]:
    words = set(re.findall(r"[a-z]+", component.lower())) - _BASIS_WORDS
    return {word.removesuffix("s") for word in words if len(word) > 2}


def _mentions(fact: VerifiedFact, words: set[str]) -> bool:
    text = {w.removesuffix("s") for w in re.findall(r"[a-z]+", heading_text(fact).lower())}
    return bool(words) and words <= text


def _crore(number: NumericValue) -> Decimal | None:
    words = re.findall(r"[a-z]+", number.unit.lower())
    factor = next((_CRORE_PER[w] for w in words if w in _CRORE_PER), None)
    return abs(number.value * factor) if factor is not None and number.value else None


def _is_inr_amount(fact: VerifiedFact, number: NumericValue) -> bool:
    unit = set(re.findall(r"[a-z]+", number.unit.lower()))
    label = set(re.findall(r"[a-z]+", number.label.lower()))
    if "%" in number.unit or (unit | label) & _COUNT_WORDS or unit & _FOREIGN_MARKS:
        return False
    if unit & _INR_MARKS or "₹" in number.unit:
        return True
    words = set(re.findall(r"[a-z]+", fact.statement.lower()))
    inr = bool(words & _INR_MARKS) or "₹" in fact.statement
    return inr and not words & _FOREIGN_MARKS and "$" not in fact.statement


def _same_line_item(fact: VerifiedFact, number: NumericValue, words: set[str]) -> bool:
    label = {
        w.removesuffix("s")
        for w in re.findall(r"[a-z]+", number.label.lower())
        if w not in _BASIS_WORDS and w not in _GENERIC_LABEL_WORDS
    }
    return words <= label if label else _mentions(fact, words)


def _year_of(number: NumericValue) -> str:
    years = _YEAR.findall(number.period)
    return years[-1] if years else ""


def _change_label(number: NumericValue) -> bool:
    return bool(_CHANGE_WORDS.search(number.label))


def _comparable_period(year: str, other_year: str, other_basis: bool) -> bool:
    """Another basis is compared in the same year only; the same basis with an adjacent year."""
    if other_basis:
        return not (year and other_year) or year == other_year
    return bool(year and other_year) and 0 < abs(int(year) - int(other_year)) <= _YEAR_REACH


def outlier_reason(
    component: str, fact: VerifiedFact, number: NumericValue, facts: Iterable[VerifiedFact]
) -> str | None:
    """Why a term figure is implausible against the same line item on another basis or year."""
    own = _crore(number)
    words = _item_words(component)
    if own is None or not words or not _is_inr_amount(fact, number):
        return None
    year = _year_of(number)
    flow = states_flow(fact)
    for other in facts:
        if other.fact_id != fact.fact_id and not _mentions(other, words):
            continue
        if states_flow(other) != flow:
            continue
        other_basis = None not in (other.scope, fact.scope) and other.scope != fact.scope
        for candidate in other.numbers:
            if candidate is number or (other.fact_id == fact.fact_id and candidate == number):
                continue
            if _change_label(candidate) or not _is_inr_amount(other, candidate):
                continue
            if not _same_line_item(other, candidate, words):
                continue
            size = _crore(candidate)
            other_year = _year_of(candidate)
            if size is None or not _comparable_period(year, other_year, other_basis):
                continue
            ratio = own / size
            if ratio > OUTLIER_RATIO or ratio * OUTLIER_RATIO < 1:
                where = other.scope.value if other_basis and other.scope else other_year
                return (
                    f"{fact.fact_id} {component} {number.value} {number.unit} is "
                    f"{ratio:.3g}x the {where} figure in {other.fact_id} "
                    f"({candidate.value} {candidate.unit}), check the unit"
                )
    return None


def subtotal_formulas(slot: InputSlot) -> tuple[tuple[tuple[int, tuple[str, ...]], ...], ...]:
    """Ways to compute a balance-sheet subtotal slot from printed totals, else ()."""
    return () if slot.derive_from else SUBTOTAL_FORMULAS.get(normalise_component(slot.slot), ())


def slot_rows(slot: InputSlot) -> tuple[str, tuple[tuple[str, ...], ...]] | None:
    """The statement and preference tiers of rows for a plain slot read from one row, else None."""
    if slot.derive_from:
        return None
    return SLOT_ROWS.get(normalise_component(slot.slot))


def search_phrase(slot: InputSlot) -> str:
    """The row the slot search looks for: the slot's first named row, else the slot name."""
    rows = slot_rows(slot)
    return rows[1][0][0] if rows else slot.slot.replace("_", " ")


def is_cash_flow_component(component: str) -> bool:
    """True for a component read from the cash flow statement (interest paid, repayments)."""
    return "cash-flow" in LINE_ITEM_SOURCE.get(normalise_component(component), "")


def unsigned_term(component: str, fact: VerifiedFact) -> bool:
    """True when a derived term enters by its absolute figure: a cash-flow component or outflow."""
    loose = any(
        same_component(component, name)
        for name, source in LINE_ITEM_SOURCE.items()
        if "cash-flow" in source
    )
    return loose or bool(_OUTFLOW_WORDS.search(fact.statement))


def states_flow(fact: VerifiedFact) -> bool:
    """True when the fact's own words say it is a cash flow (paid, repayment, outflow ...)."""
    section = getattr(fact.record, "section", None) if fact.record is not None else None
    return bool(_FLOW_WORDS.search(f"{fact.statement} {section or ''}"))


def is_flow_fact(fact: VerifiedFact) -> bool:
    """True for a cash-flow fact: category cash flow, or words that say it is one."""
    return fact.category is FactCategory.cash_flow or states_flow(fact)


def statement_fits(slot: InputSlot, fact: VerifiedFact) -> bool:
    """False for a cash flow under a profit and loss slot, or a non-flow under a cash-flow slot."""
    rows = slot_rows(slot)
    if rows is None:
        return True
    return not states_flow(fact) if rows[0] == "profit and loss" else is_flow_fact(fact)


def _names_of(component: str) -> list[str]:
    items = [component, *line_items(component)]
    return [wording for item in items for wording in item_wordings(item)]


def _slot_names(slot: InputSlot, component: str) -> bool:
    if slot.derive_from:
        return any(same_component(hint, component) for hint in slot.derive_from)
    text = _item_words(f"{slot.slot.replace('_', ' ')} {slot.description} {slot.definition}")
    return bool(_item_words(component) & text)


def term_proxy_reason(slot: InputSlot, component: str, fact: VerifiedFact) -> str | None:
    """Why a derived term stands in for something other than its component, else None."""
    name = normalise_component(component)
    if not _slot_names(slot, component):
        return f"{fact.fact_id} supplies '{component}', which is not a component of {slot.slot}"
    if "cash-flow" in LINE_ITEM_SOURCE.get(name, "") and not is_flow_fact(fact):
        return f"{fact.fact_id} is not a cash-flow figure; {component} is read from the cash flow"
    if name in BALANCE_ITEMS and states_flow(fact):
        return f"{fact.fact_id} is a cash flow, not the {component} balance"
    if name in LINE_ITEMS and not any(_mentions(fact, _item_words(w)) for w in _names_of(name)):
        return f"{fact.fact_id} states neither {component} nor any of its rows"
    return None
