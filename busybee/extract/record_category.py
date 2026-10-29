"""Guess a report category from a fact record's metric label with a keyword map.

The model is not asked for a category on table records. The first matching rule wins, so more
specific words come first: profit-like words before revenue, cash-flow words before liquidity.
Short abbreviations (PAT, PBT, EPS) match whole words only. Anything unmatched is `other`.
"""

import re

from busybee.schema.facts import FactCategory

_RULES: tuple[tuple[FactCategory, re.Pattern[str]], ...] = (
    (
        FactCategory.profitability,
        re.compile(
            r"profit|ebitda|ebit\b|\bpat\b|\bpbt\b|margin|earnings|\beps\b|\broce\b|\broe\b",
            re.IGNORECASE,
        ),
    ),
    (
        FactCategory.cash_flow,
        re.compile(r"cash flow|cfads|dscr|operating activities|investing|financing", re.I),
    ),
    (
        FactCategory.liquidity,
        re.compile(
            r"current assets|current liabilit|current ratio|quick ratio|liquid|cash and", re.I
        ),
    ),
    (
        FactCategory.debt_leverage,
        re.compile(
            r"borrowing|debt|loan|debenture|net worth|equity|leverage|gearing|interest"
            r"|finance cost",
            re.IGNORECASE,
        ),
    ),
    (FactCategory.revenue, re.compile(r"revenue|sales|turnover|income", re.IGNORECASE)),
)


def category_from_metric(metric: str) -> FactCategory:
    """The category of the first keyword rule matching the metric label, else `other`."""
    for category, pattern in _RULES:
        if pattern.search(metric):
            return category
    return FactCategory.other
