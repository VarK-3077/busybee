"""Balance-sheet section totals read in code (Craftsman v9b).

Craftsman's consolidated balance sheet closes current assets and current liabilities with rows
of figures and no label. The slot search found both rows, but the statements carried the slot's
scoring unit ("INR 3,27,177 lakh x 100"), so the number check failed on "100", and the judge
could not confirm a label the row does not print, so FSS, IRG and maximum exposure were not
computable. The total is now read from the page in code and checked against the section's rows;
when a section prints no total, the sum of its rows is used and marked derived.
"""

from decimal import Decimal

import numpy as np
from policy_helpers import BANKS_DIR, write_facts

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingResult, label_is
from busybee.policy.section_totals import (
    ROW_METHOD,
    SUM_METHOD,
    page_lines,
    section_total,
    section_total_facts,
)
from busybee.policy.slot_search import (
    Target,
    _messages,
    fill_unbound_slots,
    page_bases,
    with_unit,
)
from busybee.policy.subtotals import subtotal_binding, with_subtotals
from busybee.schema.documents import Chunk
from busybee.schema.facts import FactScope, VerifiedFact
from busybee.schema.policy import BoundInput

FSS = "financial_strength_score"
CONSOLIDATED = FactScope.consolidated
NOW = "As at March 31, 2026"
THEN = "As at March 31, 2025"


def _row(label: str, now: str, then: str = "1") -> str:
    lead = f"{label} | Note No.: 1 | " if label else ""
    return f"{lead}{NOW}: {now} | {THEN}: {then}"


PAGE = "\n".join(
    [
        "(H in lakhs)",
        "Consolidated Balance Sheet",
        "as at March 31, 2026",
        "ASSETS",
        "Non-current assets",
        f"[TABLE: Note No. | {NOW} | {THEN}]",
        _row("Property, Plant and Equipment", "3,98,074"),
        _row("Other non-current assets", "20,380"),
        _row("", "4,18,454"),
        "Current assets",
        _row("Inventories", "1,74,541"),
        "Financial assets",
        _row("Trade receivables", "1,11,054"),
        _row("Cash and cash equivalents", "14,483"),
        _row("Security Deposits", "100"),
        _row("Other Current assets", "-"),
        _row("", "3,00,178"),
        _row("Assets classified as held for sale", "34,998"),
        _row("Total Assets", "7,53,630"),
        "EQUITY AND LIABILITIES",
        "Current liabilities",
        _row("Borrowings", "92,965"),
        _row("(a) total outstanding dues of micro enterprises", "4,726"),
        "small enterprises",
        _row("Provisions", "(2,612)"),
        _row("Total Equity and Liabilities", "7,53,630"),
        "[/TABLE]",
    ]
)


def _chunks(text: str, cut: int = 3, overlap: int = 2) -> list[Chunk]:
    """The page split into chunks of `cut` lines that overlap by `overlap` lines, with offsets."""
    lines = text.split("\n")
    starts = [sum(len(x) + 1 for x in lines[:i]) for i in range(len(lines))]
    chunks: list[Chunk] = []
    first = 0
    while first < len(lines):
        last = min(first + cut, len(lines))
        body = "\n".join(lines[first:last])
        chunks.append(
            Chunk(
                chunk_id=f"D1:p5:c{len(chunks)}",
                doc_id="D1",
                page_no=5,
                index_in_page=len(chunks),
                text=body,
                char_start=starts[first],
                char_end=starts[first] + len(body),
            )
        )
        if last == len(lines):
            break
        first = last - overlap
    return chunks


def _slot(name: str):
    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)
    return next(slot for slot in spec.inputs if slot.slot == name)


def test_page_lines_rebuild_the_page_from_overlapping_chunks_once() -> None:
    lines = [line for line, _ in page_lines(_chunks(PAGE))]
    assert lines == PAGE.split("\n")


def test_unlabelled_current_assets_row_is_the_section_total_without_held_for_sale() -> None:
    found = section_total(page_lines(_chunks(PAGE)), "current assets", 2026)
    assert found is not None and not found.summed
    assert found.printed == "3,00,178"
    assert [row.label for row in found.rows][0] == "Inventories"
    assert found.total.line in found.total.chunk.text


def test_labelled_and_nested_rows_and_brackets_in_a_section() -> None:
    lines = page_lines(_chunks(PAGE))
    liabilities = section_total(lines, "current liabilities", 2026)
    assert liabilities is not None and liabilities.summed
    assert liabilities.value == Decimal(92965 + 4726 - 2612)
    nested = PAGE.replace(
        _row("Cash and cash equivalents", "14,483"),
        "\n".join([_row("Cash and cash equivalents", "14,483"), _row("", "3,00,078")]),
    )
    found = section_total(page_lines(_chunks(nested)), "current assets", 2026)
    assert found is not None and found.printed == "3,00,178"
    labelled = PAGE.replace(_row("", "3,00,178"), _row("Total Current Assets", "3,00,178"))
    found = section_total(page_lines(_chunks(labelled)), "current assets", 2026)
    assert found is not None and found.total.label == "Total Current Assets"


def test_unlabelled_row_that_matches_no_running_sum_reads_nothing() -> None:
    broken = PAGE.replace(_row("", "3,00,178"), _row("", "3,10,178"))
    assert section_total(page_lines(_chunks(broken)), "current assets", 2026) is None
    assert section_total(page_lines(_chunks(PAGE)), "current assets", 2027) is None


def _read() -> dict[str, VerifiedFact]:
    chunks = _chunks(PAGE)
    specs = load_bank(BANKS_DIR, "demo_bank").scores
    binding = BindingResult(
        unbound={(FSS, "current_assets"): "none", (FSS, "current_liabilities"): "none"},
        basis=CONSOLIDATED,
    )
    return section_total_facts(specs, binding, chunks, page_bases(chunks), 2026)


def test_section_facts_are_cited_and_bind_the_subtotal_slots() -> None:
    read = _read()
    assets, liabilities = read["current_assets"], read["current_liabilities"]
    assert assets.statement == (
        "Consolidated total current assets were INR 3,00,178 lakh as at March 31, 2026."
    )
    assert assets.verification.method == ROW_METHOD
    assert assets.scope is CONSOLIDATED
    assert liabilities.verification.method == SUM_METHOD
    assert len(liabilities.citations) == 3
    facts = [
        assets.model_copy(update={"fact_id": "F1"}),
        liabilities.model_copy(update={"fact_id": "F2"}),
    ]
    bound = subtotal_binding(_slot("current_assets"), facts, CONSOLIDATED)
    assert bound is not None and bound.value_scaled == 300178 and bound.derived_from == []
    bound = subtotal_binding(_slot("current_liabilities"), facts, CONSOLIDATED)
    assert bound is not None and bound.value_scaled == 92965 + 4726 - 2612
    assert bound.derived_from == ["F2"] and bound.note.startswith("derived: sum")


def test_own_total_wins_over_total_assets_less_non_current_assets() -> None:
    def fact(fact_id: str, label: str, value: str) -> VerifiedFact:
        return VerifiedFact(
            fact_id=fact_id,
            statement=f"Consolidated {label} was INR {value} lakh as at March 31, 2026.",
            numbers=[{"label": label, "value": value.replace(",", ""), "unit": "INR lakh"}],
        )

    facts = [
        fact("F1", "total assets", "7,53,630"),
        fact("F2", "total non-current assets", "4,18,454"),
        fact("F3", "total current assets", "3,00,178"),
    ]
    bound = subtotal_binding(_slot("current_assets"), facts, CONSOLIDATED)
    assert bound is not None and bound.fact_id == "F3" and bound.value_scaled == 300178


def test_label_ends_before_a_company_name_or_an_as_at_date() -> None:
    fact = VerifiedFact(
        fact_id="F334",
        statement=(
            "Consolidated total non-current assets for Craftsman Automation Limited as at "
            "March 31, 2026 was INR 5,35,655 lakh."
        ),
    )
    assert label_is(fact, "total non-current assets")
    assert not label_is(fact, "total assets")


def test_with_subtotals_never_binds_a_slot_twice() -> None:
    specs = load_bank(BANKS_DIR, "demo_bank").scores
    earlier = BoundInput(slot="current_assets", fact_id="F9", value=Decimal(1), value_scaled=100)
    binding = BindingResult(
        bound={FSS: [earlier]}, unbound={(FSS, "current_assets"): "none"}, basis=CONSOLIDATED
    )
    facts = [read.model_copy(update={"fact_id": "F1"}) for read in _read().values()]
    result = with_subtotals(specs, binding, facts)
    assert [b.fact_id for b in result.bound[FSS] if b.slot == "current_assets"] == ["F9"]
    assert (FSS, "current_assets") not in result.unbound


def test_slot_scoring_unit_neither_shown_to_the_model_nor_left_in_the_statement() -> None:
    target = Target(_slot("current_assets"), (FSS,), "current assets", False, "consolidated")
    chunk = _chunks(PAGE)[0]
    prompt = _messages(target, chunk, 2026)[1].content
    assert "x 100" not in prompt
    assert with_unit("Total current assets was 3,27,177 INR crore x 100.", "3,27,177", "lakh") == (
        "Total current assets was INR 3,27,177 lakh."
    )
    assert with_unit("Other bank balances were INR crore 3,395 as at", "3,395", "lakh") == (
        "Other bank balances were INR 3,395 lakh as at"
    )


async def test_slot_search_reads_the_section_total_without_a_model_call(tmp_path) -> None:
    embedder = HashingEmbedder()
    chunks = _chunks(PAGE)
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add(chunks, await embedder.embed([c.text for c in chunks]))
    store.save(tmp_path / "index")
    calls: list[str] = []

    def responder(messages: list[Message], task: str) -> str:
        calls.append(task)
        return '{"found": false}'

    spec = next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)
    spec = spec.model_copy(update={"inputs": [_slot("current_assets")]})
    binding = BindingResult(unbound={(FSS, "current_assets"): "none"}, basis=CONSOLIDATED)
    provider = MockProvider(responder)
    revenue = VerifiedFact(
        fact_id="F1",
        statement="Consolidated revenue from operations was INR 8,069 crore in FY2026.",
        numbers=[{"label": "revenue", "value": "8069", "unit": "INR crore", "period": "FY2026"}],
    )
    write_facts(tmp_path, [revenue])
    result = await fill_unbound_slots(tmp_path, provider, [spec], [revenue], binding, budget=10)
    assert "policy.slot_extract" not in calls
    assert [fact.statement for fact in result.added] == [
        "Consolidated total current assets were INR 3,00,178 lakh as at March 31, 2026."
    ]
    assert result.slots == {"current_assets"}
