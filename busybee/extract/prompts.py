"""Prompts and structured response models for the rolling-window extractor."""

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, field_validator

from busybee.schema.facts import EntryKind, FactCategory, FactRecord, FactScope

EXAMPLE_REPLY = (
    '{"entries":[{"s":"Revenue was INR 931.2 crore in FY25.","c":["D1:p12:c3"],'
    '"cat":"revenue","k":"number","i":4}],"records":[]}'
)

SYSTEM_PROMPT = (
    """You are a senior credit analyst building a notebook of every fact that \
matters for deciding whether to grant a credit line to a borrower. You read a borrower's \
document pack one window at a time.

Write only facts that bear on the credit decision: repayment capacity, leverage, liquidity, \
cash flow, ratings, defaults, litigation and regulatory actions, auditor remarks, promoter \
holding and pledge, concentration, and the figures in the checklist below. Do not write \
boilerplate (meeting notices, e-voting and proxy mechanics), governance trivia (committee \
membership, attendance, meeting counts, policy lists), CSR and ESG programmes, awards, \
product marketing or generic industry narrative; when unsure whether a fact can change the \
decision, leave it out. Cover these categories exactly:
revenue, profitability, debt_leverage, liquidity, cash_flow, credit_history, ratings, stock,
ownership_governance, litigation_regulatory, industry_market, news, other.

Classify each entry's kind as one of:
- fact: a qualitative statement about the business, owners, or events.
- number: a figure, ratio, amount, date, or other measured quantity.
- concern: a risk, weakness, breach, or open question a credit officer should notice.

Give importance on this scale, and be stingy:
1 = boilerplate.
2 = minor detail.
3 = useful context (the default; most entries).
4 = only for a topic the bank's credit policy names: external ratings and outlook, litigation,
    auditor remarks or qualifications, promoter holding and pledge, regulatory actions
    (inspections, warning letters, penalties), defaults and overdue payments, and caution-list
    sectors (customer or supplier concentration, stressed sectors).
Never give 5: the program raises the facts that feed the bank's rules and scores itself.
Rate 4 only when the entry is about one of those topics; at most a fifth of your entries.

Rules:
- Cite only chunk ids that appear in the new chunks shown to you, in square brackets,
  such as D1:p12:c3. Never invent a chunk id.
- Prefer numbers with their period and unit (for example "Revenue was INR 931.2 crore in
  FY25"), and keep restatements separate when the period or basis changes.
- If a new entry restates or replaces an earlier notebook entry, set supersedes to that
  earlier entry's id.
- Write each statement as one self-contained sentence that can be verified against the
  cited chunks. Do not speculate beyond the document.
- Stay literal. Do not add comparisons ("exceeding", "higher than", "in line with"), causal
  qualifiers ("due to", "because", "driven by") or evaluations unless those exact words are in
  the cited text. Keep the text's own subject: never swap it for a related one (a "warning
  letter" is not an "OAI status"; a subsidiary is not the group).
- Always record rating actions, the outlook and its rationale, upgrade and downgrade triggers
  ("rating may be downgraded if ..."), and each rating-history row (as "rating was X on <date>;
  Y on <date>"), even if they repeat what an earlier document already said.
- Use the source's own metric names: never rename revenue as operating income or operating
  income as revenue, and never swap one metric for a related one.
- Every entry must carry at least one chunk id from the new chunks. Never omit the chunk id.
- Never write meta-commentary about the document or the passages ("the passages do not
  mention...", "no information is available"). If a window has nothing to record, return
  no entries.
- Return only the new entries for this window, not the entries already in the notebook.

Reply format: minified JSON on one line, no indentation, no Markdown fences, using the short \
keys of the schema (s statement, c chunk_ids, cat category, k kind, i importance, sup \
supersedes; for records m metric, v value, u unit, p period, sc scope, q qualifier, pv \
previous_value, pp previous_period). Omit keys whose value is the default (empty or null). \
Example:
"""
    + EXAMPLE_REPLY
)


class NewEntry(BaseModel):
    """One entry proposed by the model for the current window."""

    model_config = ConfigDict(populate_by_name=True)

    statement: str = Field(alias="s")
    chunk_ids: list[str] = Field(default_factory=list, alias="c")
    category: FactCategory = Field(default=FactCategory.other, alias="cat")
    kind: EntryKind = Field(default=EntryKind.fact, alias="k")
    importance: int = Field(default=3, alias="i")
    supersedes: str | None = Field(default=None, alias="sup")


def _decimal_or_none(raw: object) -> object:
    """Accept "1,845.32", "(12.5)" and numbers; unreadable text (a rating grade) becomes None."""
    if not isinstance(raw, str):
        return raw
    text = raw.strip().replace(",", "").replace("\u2212", "-")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class RecordDraft(BaseModel):
    """One table row proposed as a structured fact record; code writes its sentence."""

    model_config = ConfigDict(populate_by_name=True)

    metric: str = Field(default="", alias="m")
    value: Decimal | None = Field(default=None, alias="v")
    unit: str = Field(default="", alias="u")
    period: str = Field(default="", alias="p")
    scope: FactScope | None = Field(default=None, alias="sc")
    qualifier: str | None = Field(default=None, alias="q")
    previous_value: Decimal | None = Field(default=None, alias="pv")
    previous_period: str | None = Field(default=None, alias="pp")
    chunk_ids: list[str] = Field(default_factory=list, alias="c")
    importance: int = Field(default=3, alias="i")

    @field_validator("value", "previous_value", mode="before")
    @classmethod
    def _parse_value(cls, raw: object) -> object:
        return _decimal_or_none(raw)

    @field_validator("scope", mode="before")
    @classmethod
    def _parse_scope(cls, raw: object) -> object:
        text = str(raw).strip().lower() if raw is not None else ""
        if text.startswith("consolidated"):
            return FactScope.consolidated
        return FactScope.standalone if text.replace("-", "").startswith("standalone") else None

    def to_record(self) -> FactRecord | None:
        """The schema record carried by the notebook entry, or None for an unusable row."""
        if self.value is None or not self.metric.strip():
            return None
        return FactRecord(
            metric=self.metric.strip(),
            value=self.value,
            unit=self.unit.strip(),
            period=self.period.strip(),
            scope=self.scope,
            qualifier=(self.qualifier or "").strip() or None,
            previous_value=self.previous_value,
            previous_period=(self.previous_period or "").strip() or None,
        )


class WindowOutput(BaseModel):
    """The complete structured reply for one rolling window."""

    entries: list[NewEntry]
    records: list[RecordDraft] = Field(default_factory=list)


RECORD_INSTRUCTIONS = """

This window contains table blocks. For every MATERIAL table row (a financial statement line, \
ratio, debt or liquidity figure, a rating-table row) return one item in \
`records` (short keys) instead of a sentence entry:
- m (metric): the row label exactly as printed, without the figures.
- v (value): the number in the latest-period column, as printed (no unit scaling, no commas needed).
- u (unit): the unit as printed in the table or its caption (crore, lakh, million, %, x, Rs); an \
empty string if none is printed.
- p (period): the column header the value sits under (for example FY2025-26).
- sc (scope): "consolidated" or "standalone" when the table caption or surrounding text says so, \
else null.
- q (qualifier): a short note only if the row says so (for example "restated", \
"unaudited"), else null.
- pv and pp (previous_value, previous_period): the comparison column of the same row when \
shown, else null.
- c (chunk_ids): the chunk id(s) of the chunk(s) holding the row, i (importance): 1-5 as above.
Skip rows of no credit relevance (subtotal captions, blank rows, page footers). Keep `entries` \
for prose facts, concerns and anything that is not a table row."""


def system_prompt(checklist: str = "") -> str:
    """Return the extractor system prompt, followed by the bank's policy checklist if any."""
    if not checklist.strip():
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\n{checklist.strip()}"


def build_user_prompt(
    condensed_notebook: str,
    chunks_text: str,
    *,
    window_no: int = 1,
    doc_id: str = "",
    doc_title: str = "",
    position: str = "",
    flagged: str = "",
) -> str:
    """Build the user turn containing the notebook so far and the new chunks.

    `flagged` is the digest of the rating rationales, shown as what the rating agency flagged.
    """
    document_line = ""
    if doc_id or doc_title:
        label = " ".join(part for part in (doc_id, doc_title) if part)
        document_line = f"Document: {label}\n\n"
    if position:
        document_line += f"Reading position: {position}\n\n"
    if flagged.strip():
        document_line += (
            "What the rating agency flagged (key points of the rating rationale, already read; "
            "a pointer to what matters, not a source to cite):\n"
            f"{flagged.strip()}\n\n"
        )
    notebook = condensed_notebook.strip() or "(empty notebook)"
    records = RECORD_INSTRUCTIONS if "[TABLE:" in chunks_text else ""
    return (
        f"{document_line}"
        f"Condensed notebook so far:\n{notebook}\n\n"
        f"New chunks for window {window_no}:\n{chunks_text}\n\n"
        "Extract the new entries. Cite only the chunk ids shown above and return JSON "
        f"matching WindowOutput.{records}"
    )


MAX_LIMITED_ENTRIES = 25
LIMITED_ENTRIES_INSTRUCTION = (
    "\n\nYour previous reply for this text was cut off because it was too long. Return at most "
    f"{MAX_LIMITED_ENTRIES} entries in total (entries and records together), ordered from most "
    "to least important, and keep every statement short."
)

build_window_prompt = build_user_prompt
