"""Check Lean quantification: generated defs, successful proofs, and failed compiles."""

from decimal import Decimal

import pytest

from busybee.infer.prompts import LeanClaim
from busybee.infer.quantify import (
    QuantifyError,
    build_lean_source,
    common_scale,
    lean_failure_message,
    quantify_inference,
    scaled_int,
)
from busybee.lean.toolchain import find_lake, find_lean
from busybee.schema.facts import (
    Citation,
    FactCategory,
    NumericValue,
    VerifiedFact,
)
from busybee.schema.lean import CompileResult, LeanError
from busybee.schema.report import Inference

pytestmark = pytest.mark.skipif(
    find_lean() is None or find_lake() is None,
    reason="Lean toolchain is not installed",
)


def _fact(
    fact_id: str,
    value: str,
    unit: str = "crore",
    *,
    with_number: bool = True,
) -> VerifiedFact:
    numbers = [NumericValue(label="Amount", value=Decimal(value), unit=unit)] if with_number else []
    return VerifiedFact(
        fact_id=fact_id,
        statement=f"{fact_id} is a verified amount.",
        category=FactCategory.debt_leverage,
        citations=[Citation(chunk_id="D1:p2:c1", doc_id="D1", page_no=2)],
        numbers=numbers,
    )


def _inference(quantitative: bool = True) -> Inference:
    return Inference(
        inference_id="I001",
        opinion="Debt is at most three times revenue.",
        fact_ids=["F001", "F002"],
        reasoning="F001 and F002 support the comparison.",
        confidence=0.8,
        quantitative=quantitative,
    )


def test_scaled_int_normalises_units_to_a_common_scale() -> None:
    def number(value: str, unit: str) -> NumericValue:
        return NumericValue(label="x", value=Decimal(value), unit=unit)

    assert scaled_int(number("12.34", "crore"), 100) == 1234
    assert scaled_int(number("5", "lakh"), 100) == 5
    assert scaled_int(number("2", "million"), 10) == 2
    assert scaled_int(number("1", "billion"), 1) == 100
    assert scaled_int(number("12.5", "%"), 10) == 125
    assert scaled_int(number("50", "bps"), 100) == 50
    assert common_scale([number("1.25", ""), number("3.4", ""), number("84", "%")]) == 100
    assert common_scale([number("1", ""), number("2", "")]) == 1
    assert common_scale([number("0.123456", "")]) == 10_000


def test_build_lean_source_contains_provenance_and_claim() -> None:
    claim = LeanClaim(
        facts={"revenue": "F001", "debt": "F002"},
        claim="debt <= 3 * revenue",
    )
    source = build_lean_source(_inference(), claim, [_fact("F001", "1000"), _fact("F002", "2000")])
    assert "import BusyBee.Common" in source
    assert "def revenue : Int := 1000 -- F001 D1:p2:c1" in source
    assert "def debt : Int := 2000 -- F002 D1:p2:c1" in source
    assert "theorem claim : debt <= 3 * revenue := by" in source
    assert "-- scale: x1\n" in source


async def test_quantify_success_attaches_compiled_artifact(tmp_path) -> None:
    claim = LeanClaim(
        facts={"revenue": "F001", "debt": "F002"},
        claim="debt <= 3 * revenue",
    )
    result = await quantify_inference(
        _inference(),
        claim,
        [_fact("F001", "1000"), _fact("F002", "2000")],
        output_dir=tmp_path,
        run_id="run1",
    )
    assert result.lean is not None
    assert result.lean.kind.value == "inference"
    assert result.lean.artifact_id == "run1:I001"
    assert result.lean.theorems == ["claim"]
    assert result.lean.compile is not None and result.lean.compile.ok
    assert (tmp_path / "Inference_I001.lean").is_file()


async def test_quantify_failure_keeps_inference_with_failed_artifact(tmp_path) -> None:
    claim = LeanClaim(facts={"debt": "F002"}, claim="debt < 0")
    result = await quantify_inference(
        _inference(),
        claim,
        [_fact("F001", "1000"), _fact("F002", "2000")],
        output_dir=tmp_path,
        run_id="run1",
    )
    assert result.opinion == "Debt is at most three times revenue."
    assert result.lean is not None
    assert result.lean.compile is not None
    assert result.lean.compile.ok is False
    assert result.lean.source
    assert (tmp_path / "Inference_I001.lean").is_file()


async def test_missing_number_is_a_failed_artifact_without_crashing(tmp_path) -> None:
    claim = LeanClaim(facts={"debt": "F002"}, claim="debt < 0")
    result = await quantify_inference(
        _inference(),
        claim,
        [_fact("F002", "0", with_number=False)],
        output_dir=tmp_path,
        run_id="run1",
    )
    assert result.lean is not None
    assert result.lean.compile is not None
    assert result.lean.compile.ok is False
    assert "no numeric value" in result.lean.compile.stderr
    assert (tmp_path / "Inference_I001.lean").is_file()


def _multi_number_fact() -> VerifiedFact:
    return VerifiedFact(
        fact_id="F003",
        statement="Net debt to EBITDA was 2.7 times, covenant 3.5 times.",
        category=FactCategory.debt_leverage,
        citations=[Citation(chunk_id="D1:p2:c1", doc_id="D1", page_no=2)],
        numbers=[
            NumericValue(label="ratio", value=Decimal("2.7")),
            NumericValue(label="limit", value=Decimal("3.5")),
        ],
    )


def test_fact_reference_with_hash_picks_that_number() -> None:
    claim = LeanClaim(facts={"current": "F003", "limit": "F003#3.5"}, claim="current < limit")
    source = build_lean_source(_inference(), claim, [_multi_number_fact()])
    assert "def current : Int := 27 -- F003" in source
    assert "def limit : Int := 35 -- F003" in source


def test_unknown_number_selector_lists_the_available_numbers() -> None:
    claim = LeanClaim(facts={"limit": "F003#9.9"}, claim="limit > 0")
    with pytest.raises(QuantifyError, match=r"no number 9.9 \(it has: 2.7, 3.5\)"):
        build_lean_source(_inference(), claim, [_multi_number_fact()])


def test_decimal_literal_in_claim_is_rejected_with_advice() -> None:
    claim = LeanClaim(facts={"ratio": "F003"}, claim="ratio >= 1.25")
    with pytest.raises(QuantifyError, match="decimal literal 1.25"):
        build_lean_source(_inference(), claim, [_multi_number_fact()])


async def test_multi_number_claim_compiles(tmp_path) -> None:
    claim = LeanClaim(facts={"current": "F003", "limit": "F003#3.5"}, claim="current < limit")
    result = await quantify_inference(
        _inference(), claim, [_multi_number_fact()], output_dir=tmp_path
    )
    assert result.lean is not None and result.lean.compile is not None
    assert result.lean.compile.ok


def test_failure_message_carries_the_lean_error_even_when_stderr_is_empty() -> None:
    failed = CompileResult(
        ok=False,
        stdout="x.lean:24:2: error: Tactic `decide` proved that the proposition\n  p\nis false\n",
        errors=[LeanError(line=24, col=2, message="Tactic `decide` proved\np\nis false")],
    )
    assert lean_failure_message(failed) == "line 24: Tactic `decide` proved p is false"
    assert lean_failure_message(CompileResult(ok=False, stdout="raw text")) == "raw text"
    assert lean_failure_message(CompileResult(ok=False)) == "unknown error"


def _fact_with(fact_id: str, statement: str, numbers: list[tuple[str, str]]) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=FactCategory.cash_flow,
        citations=[Citation(chunk_id="D3:p2:c0", doc_id="D3", page_no=2)],
        numbers=[NumericValue(label="n", value=Decimal(v), unit=u) for v, u in numbers],
    )


def _i003_facts() -> list[VerifiedFact]:
    return [
        _fact_with(
            "F046",
            "DSCR was 1.78 times, covenant not less than 1.25 times.",
            [("1.78", ""), ("1.25", "")],
        ),
        _fact_with(
            "F059",
            "Interest coverage was 3.4 times, covenant not less than 2.5 times.",
            [("3.4", ""), ("2.5", "")],
        ),
    ]


_I003_CLAIM = "dscr > dscr_covenant && interest_coverage > interest_covenant"


def test_i003_as_the_model_wrote_it_is_rejected_for_duplicate_numbers() -> None:
    claim = LeanClaim(
        facts={
            "dscr": "F046",
            "dscr_covenant": "F046",
            "interest_coverage": "F059",
            "interest_covenant": "F059",
        },
        claim=_I003_CLAIM,
    )
    with pytest.raises(QuantifyError, match="dscr and dscr_covenant are the same number"):
        build_lean_source(_inference(), claim, _i003_facts())


async def test_i003_with_selectors_uses_one_scale_and_compiles(tmp_path) -> None:
    claim = LeanClaim(
        facts={
            "dscr": "F046",
            "dscr_covenant": "F046#1.25",
            "interest_coverage": "F059",
            "interest_covenant": "F059#2.5",
        },
        claim=_I003_CLAIM,
    )
    result = await quantify_inference(_inference(), claim, _i003_facts(), output_dir=tmp_path)
    assert result.lean is not None and result.lean.compile is not None
    assert result.lean.compile.ok, result.lean.compile
    source = result.lean.source
    assert "-- scale: x100" in source
    assert "def dscr : Int := 178" in source
    assert "def dscr_covenant : Int := 125" in source
    assert "def interest_coverage : Int := 340" in source
    assert "def interest_covenant : Int := 250" in source


def test_mixed_units_are_rejected_with_a_clear_message() -> None:
    facts = [
        _fact_with(
            "F062",
            "Rs 120 crore expansion capped at 3.5 times.",
            [("120", "INR crore"), ("3.5", "")],
        ),
        _fact_with("F056", "Net debt to EBITDA was 2.7 times.", [("2.7", "")]),
        _fact_with("F043", "Utilisation was 84%.", [("84", "%")]),
    ]
    claim = LeanClaim(facts={"ratio": "F056", "limit": "F062"}, claim="ratio < limit")
    with pytest.raises(QuantifyError, match=r"mixes incompatible units: .*limit \(INR crore\)"):
        build_lean_source(_inference(), claim, facts)
    fixed = LeanClaim(facts={"ratio": "F056", "limit": "F062#3.5"}, claim="ratio < limit")
    assert "-- scale: x10" in build_lean_source(_inference(), fixed, facts)
    percent = LeanClaim(facts={"ratio": "F056", "use": "F043"}, claim="ratio < use")
    with pytest.raises(QuantifyError, match="incompatible units"):
        build_lean_source(_inference(), percent, facts)


def test_chained_comparison_is_rejected() -> None:
    claim = LeanClaim(facts={"a": "F003", "b": "F003#3.5"}, claim="a < b < b")
    with pytest.raises(QuantifyError, match="chained comparison"):
        build_lean_source(_inference(), claim, [_multi_number_fact()])
