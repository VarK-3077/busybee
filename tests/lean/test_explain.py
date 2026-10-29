"""Tests for parsing Lean sections and rendering best-effort English."""

from busybee.lean.explain.build import explain_source
from busybee.lean.explain.english import english_for
from busybee.lean.explain.parse import parse_sections
from busybee.lean.project import project_dir


def _example_source() -> str:
    return (project_dir() / "BusyBee" / "Example.lean").read_text(encoding="utf-8")


def test_example_parses_into_the_expected_sections_and_items() -> None:
    explanation = explain_source(_example_source())
    assert [section.title for section in explanation.sections] == [
        "Scaled facts",
        "Threshold checks",
        "Arithmetic",
    ]
    assert [item.name for item in explanation.sections[0].items] == ["netDebt", "ebitda"]
    assert [item.name for item in explanation.sections[1].items] == [
        "leverage_within_limit",
        "interest",
        "interest_cover_at_least_two",
    ]
    assert [item.name for item in explanation.sections[2].items] == [
        "headroom_positive",
        "leverageGrade",
    ]
    assert explanation.sections[0].items[0].kind == "def"
    assert explanation.sections[1].items[0].kind == "theorem"


def test_doc_comment_is_kept_beside_the_mechanical_reading() -> None:
    explanation = explain_source(_example_source())
    net_debt = explanation.sections[0].items[0]
    assert net_debt.doc == "Net debt for FY26, in INR crore × 100."
    assert net_debt.english == "net debt is defined as 125000 (scaled), from fact F012 (D1:p214:c2)"
    assert "-- F012 D1:p214:c2" in net_debt.lean


def test_english_uses_the_operator_table_and_spaces_names() -> None:
    source = """-- SECTION: Mapping
theorem at_most : a * b ≤ c + d := by decide
theorem at_least : a ≥ b := by decide
theorem logic : a ∧ b ∨ ¬ c → d := by decide
def choose (x : Int) : Int := if x ≤ 0 then 1 else 2
"""
    declarations = {
        declaration.name: declaration
        for section in parse_sections(source)
        for declaration in section.declarations
    }
    assert "times" in english_for(declarations["at_most"])
    assert "is at most" in english_for(declarations["at_most"])
    assert "plus" in english_for(declarations["at_most"])
    assert "is at least" in english_for(declarations["at_least"])
    logic = english_for(declarations["logic"])
    assert "and" in logic
    assert "or" in logic
    assert "not" in logic
    assert "implies" in logic
    choose = english_for(declarations["choose"])
    assert "if" in choose and "then" in choose and "else" in choose
    assert "0" in choose and "1" in choose and "2" in choose


def test_english_spaces_snake_and_camel_case_names() -> None:
    source = """-- SECTION: Names
theorem net_debt_limit : 1 ≤ 2 := by decide
def ratioAtMost (a b : Int) : Int := a + b
"""
    english = [
        english_for(item) for section in parse_sections(source) for item in section.declarations
    ]
    assert "net debt limit" in english[0]
    assert "ratio at most" in english[1]


def test_multiline_doc_and_signature_are_captured() -> None:
    source = """-- SECTION: Long
/-- A multi
line doc. -/
theorem multi
    (h : 0 < x) :
    0 < x + 1 := by
  omega
"""
    sections = parse_sections(source)
    declaration = sections[0].declarations[0]
    assert declaration.doc == "A multi line doc."
    assert declaration.name == "multi"
    assert "0 < x + 1" in declaration.signature
    assert declaration.body.startswith("by")


def test_mechanical_reading_names_theorem_and_def_provenance() -> None:
    source = """-- SECTION: Facts
def cash : Int := 2140 -- F007 D1:p2:c0
def debt : Int := 5 -- F004 D1:p2:c0 D2:p3:c0 F007 D1:p2:c0
theorem claim : cash < maturities := by decide
"""
    declarations = {d.name: d for s in parse_sections(source) for d in s.declarations}
    assert english_for(declarations["cash"]) == (
        "cash is defined as 2140 (scaled), from fact F007 (D1:p2:c0)"
    )
    assert english_for(declarations["debt"]) == (
        "debt is defined as 5 (scaled), from facts F004 (D1:p2:c0, D2:p3:c0) and F007 (D1:p2:c0)"
    )
    assert english_for(declarations["claim"]) == "claim: cash is less than maturities"
