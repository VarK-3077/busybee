"""Citations, notebook entries, verified facts, and dropped-entry audit records."""

import re
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class FactCategory(StrEnum):
    """The credit-review categories used to group facts in the report."""

    revenue = "revenue"
    profitability = "profitability"
    debt_leverage = "debt_leverage"
    liquidity = "liquidity"
    cash_flow = "cash_flow"
    credit_history = "credit_history"
    ratings = "ratings"
    stock = "stock"
    ownership_governance = "ownership_governance"
    litigation_regulatory = "litigation_regulatory"
    industry_market = "industry_market"
    news = "news"
    other = "other"


class EntryKind(StrEnum):
    """Whether a notebook entry is a fact, a number, or a concern."""

    fact = "fact"
    number = "number"
    concern = "concern"


class VerificationStatus(StrEnum):
    """The final citation status assigned by the verify stage."""

    supported = "supported"
    resupported = "resupported"
    unsupported = "unsupported"
    conflicted = "conflicted"


class Citation(BaseModel):
    """A pointer to the exact chunk supporting a statement.

    `source` is None for a document chunk and `bank_input` for a figure the bank supplied.
    """

    chunk_id: str
    doc_id: str
    page_no: int
    quote: str = ""
    source: str | None = None


class NumericValue(BaseModel):
    """A labelled number extracted from a statement, with its unit and period."""

    label: str
    value: Decimal
    unit: str = ""
    period: str = ""


class FactScope(StrEnum):
    """Whether a fact is about the consolidated group or the standalone company."""

    consolidated = "consolidated"
    standalone = "standalone"


class FactRecord(BaseModel):
    """A structured numeric fact: one table row (or figure) as fields, not prose.

    `metric` is the row label as printed, `unit` the unit as printed (crore, lakh, %, x, ...),
    `period` the column header it was read under, and `previous_value` / `previous_period` the
    comparison column when the row shows one. `section` is the heading path the row sits under
    ("Non Current Assets > Financial Assets"), set by code from the table text. Code renders the
    statement from these fields.
    """

    metric: str
    value: Decimal
    unit: str = ""
    period: str = ""
    scope: FactScope | None = None
    qualifier: str | None = None
    previous_value: Decimal | None = None
    previous_period: str | None = None
    section: str | None = None


class NotebookEntry(BaseModel):
    """A candidate fact written by the rolling extractor."""

    entry_id: str
    statement: str
    citations: list[Citation] = Field(default_factory=list)
    category: FactCategory = FactCategory.other
    kind: EntryKind = EntryKind.fact
    importance: int = 3
    window_no: int = 0
    doc_id: str = ""
    supersedes: str | None = None
    added_by: str | None = None
    citation_inferred: bool = False
    record: FactRecord | None = None


class Verification(BaseModel):
    """How a notebook entry's citation was checked."""

    status: VerificationStatus
    method: str = ""
    notes: str = ""


class ConflictNote(BaseModel):
    """A cross-document disagreement: the other fact, why they disagree, and how it was settled."""

    fact_id: str
    note: str
    resolved_by: str = "source_priority"


def scope_from_statement(statement: str) -> FactScope | None:
    """Consolidated or standalone when the statement names exactly one of them, else None."""
    lowered = statement.lower()
    consolidated = re.search(r"\bconsolidated\b", lowered) is not None
    standalone = re.search(r"\bstand[- ]?alone\b", lowered) is not None
    if consolidated == standalone:
        return None
    return FactScope.consolidated if consolidated else FactScope.standalone


class VerifiedFact(BaseModel):
    """A fact that passed relevance and citation checks, keyed by fact_id in reports."""

    fact_id: str
    statement: str
    category: FactCategory = FactCategory.other
    citations: list[Citation] = Field(default_factory=list)
    numbers: list[NumericValue] = Field(default_factory=list)
    verification: Verification | None = None
    importance: int = 3
    source_entry_id: str | None = None
    added_by: str | None = None
    conflicts: list[ConflictNote] = Field(default_factory=list)
    scope: FactScope | None = None
    record: FactRecord | None = None

    @model_validator(mode="after")
    def _derive_scope(self) -> "VerifiedFact":
        if self.scope is None and self.record is not None:
            self.scope = self.record.scope
        if self.scope is None:
            self.scope = scope_from_statement(self.statement)
        return self


class DroppedEntry(BaseModel):
    """An entry removed from the report, retained with the reason and stage."""

    entry: NotebookEntry
    reason: str
    stage: str
