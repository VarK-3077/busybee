"""Deterministic duplicate merging: same category, same numbers, similar wording."""

from decimal import Decimal

from busybee.schema.facts import (
    Citation,
    FactCategory,
    NumericValue,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.verify.dedupe import dedupe_facts, jaccard, statement_tokens


def _fact(
    entry_id: str,
    statement: str,
    values: list[str],
    chunk: str,
    category: FactCategory = FactCategory.revenue,
    unit: str = "",
    importance: int = 3,
) -> VerifiedFact:
    return VerifiedFact(
        fact_id="",
        statement=statement,
        category=category,
        citations=[Citation(chunk_id=chunk, doc_id=chunk.split(":")[0], page_no=1)],
        numbers=[NumericValue(label="n", value=Decimal(v), unit=unit) for v in values],
        verification=Verification(status=VerificationStatus.supported, notes="ok"),
        source_entry_id=entry_id,
        importance=importance,
    )


def test_tokens_ignore_case_punctuation_and_stopwords() -> None:
    assert statement_tokens("Revenue was INR 1,200.5 crore, in the year!") == {
        "revenue",
        "inr",
        "1200",
        "5",
        "crore",
        "year",
    }
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_duplicates_merge_with_union_of_citations() -> None:
    first = _fact("D1:E1", "Revenue was INR 931.2 crore in FY25.", ["931.2"], "D1:p1:c0")
    second = _fact("D2:E7", "Revenue was INR 931.20 crore in FY25", ["931.20"], "D2:p4:c1")
    third = _fact("D3:E2", "Revenue was INR 931.2 crore in FY25.", ["931.2"], "D1:p1:c0")
    merged = dedupe_facts([first, second, third])
    assert len(merged) == 1
    fact = merged[0]
    assert fact.statement == first.statement
    assert fact.source_entry_id == "D1:E1"
    assert [c.chunk_id for c in fact.citations] == ["D1:p1:c0", "D2:p4:c1"]
    assert fact.verification is not None
    assert "D2:E7" in fact.verification.notes and "D3:E2" in fact.verification.notes
    assert fact.verification.notes.startswith("ok")


def test_different_values_category_or_wording_do_not_merge() -> None:
    base = _fact("E1", "Revenue was INR 931.2 crore in FY25.", ["931.2"], "D1:p1:c0")
    other_value = _fact("E2", "Revenue was INR 845.5 crore in FY25.", ["845.5"], "D1:p1:c1")
    other_category = _fact(
        "E3", "Revenue was INR 931.2 crore in FY25.", ["931.2"], "D2:p1:c0", FactCategory.other
    )
    other_wording = _fact("E4", "Exports shipped to Germany grew 931.2", ["931.2"], "D2:p2:c0")
    facts = [base, other_value, other_category, other_wording]
    assert len(dedupe_facts(facts)) == 4


def test_facts_without_numbers_are_never_merged() -> None:
    one = _fact("E1", "The auditor issued an unmodified opinion.", [], "D1:p1:c0")
    two = _fact("E2", "The auditor issued an unmodified opinion.", [], "D2:p1:c0")
    assert len(dedupe_facts([one, two])) == 2


def test_subset_value_set_merges_keeping_richer_statement_and_earlier_source() -> None:
    poor = _fact("D1:E1", "Revenue was INR 931.2 crore in FY25.", ["931.2"], "D1:p1:c0")
    rich = _fact(
        "D2:E7",
        "Revenue was INR 931.2 crore in FY25, up 10.1% from INR 845.5 crore.",
        ["931.2", "10.1", "845.5"],
        "D2:p4:c1",
    )
    merged = dedupe_facts([poor, rich])

    assert len(merged) == 1
    assert merged[0].statement == rich.statement
    assert len(merged[0].numbers) == 3
    assert merged[0].source_entry_id == "D1:E1"
    assert [c.chunk_id for c in merged[0].citations] == ["D1:p1:c0", "D2:p4:c1"]
    assert "merged duplicate D2:E7" in merged[0].verification.notes


def test_subset_keeps_earlier_richer_fact_and_rejects_partial_overlap() -> None:
    rich = _fact(
        "D1:E1", "Total borrowings were INR 382.0 crore, 351.0 prior.", ["382", "351"], "D1:p1:c0"
    )
    poor = _fact("D2:E2", "Total borrowings were INR 382.0 crore.", ["382"], "D2:p1:c0")
    other = _fact(
        "D3:E3", "Total borrowings were INR 382.0 crore, 400 later.", ["382", "400"], "D3:p1:c0"
    )

    merged = dedupe_facts([rich, poor, other])

    assert [f.source_entry_id for f in merged] == ["D1:E1", "D3:E3"]
    assert merged[0].statement == rich.statement


def test_subset_requires_same_category_and_wording_overlap() -> None:
    a = _fact("D1:E1", "Revenue was INR 931.2 crore.", ["931.2"], "D1:p1:c0")
    b = _fact(
        "D2:E2",
        "Revenue was INR 931.2 crore, EBITDA 10.",
        ["931.2", "10"],
        "D2:p1:c0",
        FactCategory.profitability,
    )
    c = _fact(
        "D3:E3", "Plant capacity expansion cost 931.2 spindles planned", ["931.2", "5"], "D3:p1:c0"
    )

    assert len(dedupe_facts([a, b, c])) == 3


def test_fiscal_year_spelling_does_not_block_a_real_pair_from_workspace() -> None:
    short = _fact(
        "D1:E1",
        "Revenue from operations was INR 931.2 crore in FY2024-25, up from INR 845.5 crore "
        "in FY2023-24.",
        ["931.2", "845.5"],
        "D1:p1:c0",
    )
    long = _fact(
        "D2:E2",
        "Revenue from operations was INR 931.2 crore in FY25, an increase of 10.1% from "
        "INR 845.5 crore in FY24.",
        ["931.2", "10.1", "845.5"],
        "D2:p1:c0",
    )
    merged = dedupe_facts([short, long])
    assert len(merged) == 1 and "10.1%" in merged[0].statement


def test_real_run_pairs_merge_on_shared_values_or_unit_and_subject() -> None:
    f001 = _fact(
        "E1",
        "Revenue from operations was INR 931.2 crore in FY25, an increase of 10.1% from "
        "INR 845.5 crore in FY24.",
        ["931.2", "10.1", "845.5"],
        "D1:p1:c0",
        unit="x",
    )
    f048 = _fact(
        "E2",
        "Acme Textiles Limited's revenue grew by 10.1% to Rs 931.2 crore in FY25.",
        ["10.1", "931.2"],
        "D2:p1:c0",
    )
    f015 = _fact(
        "E3",
        "Exports contributed 34% of revenue in FY25, up from 31% in FY24, with the United "
        "Kingdom, Germany, and the United States as the main destinations.",
        ["34", "31"],
        "D1:p2:c0",
        unit="%",
    )
    f050 = _fact(
        "E4",
        "Exports accounted for 34% of Acme Textiles Limited's revenue in FY25.",
        ["34"],
        "D2:p2:c0",
        unit="%",
    )
    f016 = _fact(
        "E5",
        "The top five customers accounted for 41% of revenue in FY25, with the largest single "
        "customer accounting for 14% of revenue.",
        ["41", "14"],
        "D1:p3:c0",
        unit="%",
    )
    f051 = _fact(
        "E6",
        "The top five customers contributed 41% of Acme Textiles Limited's revenue in FY25.",
        ["41"],
        "D2:p3:c0",
        unit="%",
    )
    merged = dedupe_facts([f001, f015, f016, f048, f050, f051])
    assert [f.source_entry_id for f in merged] == ["E1", "E3", "E5"]


def test_single_shared_percent_needs_the_same_subject() -> None:
    exports = _fact("E1", "Exports contributed 34% of revenue.", ["34"], "D1:p1:c0", unit="%")
    margin = _fact("E2", "EBITDA margin was 34% of sales.", ["34"], "D2:p1:c0", unit="%")
    assert len(dedupe_facts([exports, margin])) == 2


def test_largest_customer_does_not_merge_with_top_five() -> None:
    largest = _fact(
        "E1", "The largest customer accounted for 14% of revenue.", ["14"], "D1:p1:c0", unit="%"
    )
    top_five = _fact(
        "E2", "The top five customers accounted for 41% of revenue.", ["41"], "D2:p1:c0", unit="%"
    )
    assert len(dedupe_facts([largest, top_five])) == 2


def test_different_fiscal_years_do_not_merge() -> None:
    fy25 = _fact("E1", "Exports contributed 34% of revenue in FY25.", ["34"], "D1:p1:c0", unit="%")
    fy24 = _fact(
        "E2", "Exports contributed 34% of revenue in FY2023-24.", ["34"], "D2:p1:c0", unit="%"
    )
    same = _fact(
        "E3", "Exports contributed 34% of revenue in FY2024-25.", ["34"], "D3:p1:c0", unit="%"
    )
    assert [f.source_entry_id for f in dedupe_facts([fy25, fy24, same])] == ["E1", "E2"]


def test_merge_keeps_the_higher_importance() -> None:
    low = _fact("E1", "Revenue was INR 931.2 crore.", ["931.2"], "D1:p1:c0", importance=2)
    high = _fact("E2", "Revenue was INR 931.2 crore.", ["931.2"], "D2:p1:c0", importance=5)
    assert dedupe_facts([low, high])[0].importance == 5


def test_shared_money_unit_words_are_not_a_shared_subject() -> None:
    exposure = _fact(
        "E1", "Aggregate bank exposure is Rs 432.0 crore.", ["432.0"], "D1:p1:c0", unit="INR crore"
    )
    rated = _fact(
        "E2",
        "Total bank facilities rated: Rs 432.0 crore (term loans Rs 214.0 crore).",
        ["432.0", "214.0"],
        "D2:p1:c0",
        unit="INR crore",
    )
    assert len(dedupe_facts([exposure, rated])) == 2


_F046 = (
    "Total bank facilities rated by Meridian Ratings amount to Rs 432.0 crore, comprising "
    "Rs 214.0 crore in long-term term loans, Rs 190.0 crore in fund-based working capital, "
    "and Rs 28.0 crore in non-fund-based limits."
)
_F035 = (
    "The company has not provided for the INR 14.2 crore GST demand, as management believes "
    "it will succeed on appeal."
)
_F036 = (
    "Contingent liabilities not provided for totaled INR 21.6 crore at 31 March 2025, "
    "comprising the INR 14.2 crore GST demand and INR 7.4 crore of bank guarantees and "
    "disputed customs duty."
)


def _debt(entry: str, statement: str, values: list[str]) -> VerifiedFact:
    return _fact(
        entry, statement, values, f"D1:p{entry[-1]}:c0", FactCategory.debt_leverage, "INR crore"
    )


def test_different_facilities_sharing_an_amount_do_not_merge() -> None:
    facility_list = _debt("D1:E1", _F046, ["432.0", "214.0", "190.0", "28.0"])
    term_loans = _debt(
        "D1:E2", "Term loans outstanding were Rs 214.0 crore as of 31 March 2025.", ["214.0"]
    )
    non_fund = _debt(
        "D1:E3",
        "Non-fund-based limits for letters of credit and guarantees are Rs 28.0 crore.",
        ["28.0"],
    )
    assert len(dedupe_facts([facility_list, term_loans, non_fund])) == 3


def test_gst_demand_and_contingent_liabilities_do_not_merge() -> None:
    gst = _fact(
        "D1:E1", _F035, ["14.2"], "D1:p1:c0", FactCategory.litigation_regulatory, "INR crore"
    )
    contingent = _fact(
        "D1:E2",
        _F036,
        ["21.6", "14.2", "7.4"],
        "D1:p2:c0",
        FactCategory.litigation_regulatory,
        "INR crore",
    )
    assert len(dedupe_facts([gst, contingent])) == 2


def test_the_intended_cross_document_pairs_still_merge() -> None:
    pairs = [
        (
            "Revenue from operations was INR 931.2 crore in FY25, an increase of 10.1% from "
            "INR 845.5 crore in FY24.",
            ["931.2", "10.1", "845.5"],
            "Acme Textiles Limited's revenue grew by 10.1% to Rs 931.2 crore in FY25.",
            ["10.1", "931.2"],
        ),
        (
            "Exports contributed 34% of revenue in FY25, up from 31% in FY24, with the United "
            "Kingdom, Germany, and the United States as the main destinations.",
            ["34", "31"],
            "Exports accounted for 34% of Acme Textiles Limited's revenue in FY25.",
            ["34"],
        ),
        (
            "The top five customers accounted for 41% of revenue in FY25, with the largest "
            "single customer, a European fast-fashion retailer, accounting for 14% of revenue.",
            ["41", "14"],
            "The top five customers contributed 41% of Acme Textiles Limited's revenue in FY25.",
            ["41"],
        ),
    ]
    for first, first_values, second, second_values in pairs:
        facts = [
            _fact("D1:E1", first, first_values, "D1:p1:c0", unit="%"),
            _fact("D2:E1", second, second_values, "D2:p1:c0", unit="%"),
        ]
        assert len(dedupe_facts(facts)) == 1, second


def _money(statement: str, value: str, unit: str, **kw) -> VerifiedFact:
    return VerifiedFact(
        fact_id="",
        statement=statement,
        category=FactCategory.revenue,
        numbers=[NumericValue(label="revenue", value=Decimal(value), unit=unit)],
        **kw,
    )


def test_lakh_and_crore_amounts_merge_across_period_phrasings() -> None:
    crore = _money(
        "Revenue from operations was INR 1,686.07 crore in FY 2025-26.", "1686.07", "INR crore"
    )
    lakh = _money(
        "Total revenue from operations rose to INR 1,68,607.08 lakhs, year ended March 31, 2026.",
        "168607.08",
        "INR lakh",
    )
    assert len(dedupe_facts([crore, lakh])) == 1


def test_amount_tolerance_and_year_guard_and_scope_guard() -> None:
    crore = _money(
        "Revenue from operations was INR 1,686.07 crore in FY 2025-26.", "1686.07", "INR crore"
    )
    off = _money("Revenue from operations was INR 1,70,000 lakhs in FY2026.", "170000", "INR lakh")
    older = _money(
        "Revenue from operations was INR 1,68,607.08 lakhs in FY2025.", "168607.08", "INR lakh"
    )
    standalone = _money(
        "Standalone revenue from operations was INR 1,686.07 crore in FY 2025-26.",
        "1686.07",
        "INR crore",
    )
    consolidated = _money(
        "Consolidated revenue from operations was INR 1,68,607.08 lakhs in FY2026.",
        "168607.08",
        "INR lakh",
    )
    assert len(dedupe_facts([crore, off])) == 2
    assert len(dedupe_facts([crore, older])) == 2
    assert len(dedupe_facts([standalone, consolidated])) == 2
