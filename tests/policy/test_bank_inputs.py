"""Bank inputs become synthetic verified facts: ids continue the F sequence, merge is idempotent."""

import json
from decimal import Decimal
from pathlib import Path

from policy_helpers import write_facts

from busybee.policy.bank_inputs import bank_input_facts, read_all_facts, sync_bank_input_facts
from busybee.schema.facts import FactCategory, NumericValue, VerifiedFact
from busybee.schema.run import RunConfig


def _cfg(tmp_path: Path, **updates: Decimal | None) -> RunConfig:
    return RunConfig(
        run_id="r",
        docs_dir=tmp_path,
        bank_id="demo_bank",
        out_dir=tmp_path / "out",
        workspace_dir=tmp_path,
        **updates,
    )


def _existing() -> list[VerifiedFact]:
    return [
        VerifiedFact(
            fact_id=f"F{n:03d}",
            statement=f"Revenue was {n} crore",
            numbers=[NumericValue(label="r", value=Decimal(n), unit="crore")],
        )
        for n in (1, 7)
    ]


def test_facts_continue_the_id_sequence_with_a_credit_request_citation(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, proposed_exposure=Decimal("150.0"), projected_turnover=Decimal("1100"))
    merged = bank_input_facts(cfg, _existing())
    exposure, turnover = merged[-2:]
    assert (exposure.fact_id, turnover.fact_id) == ("F008", "F009")
    assert exposure.statement == (
        "Bank input: proposed exposure INR 150 crore (from the credit request)"
    )
    assert exposure.category is FactCategory.other
    assert exposure.numbers[0].value == Decimal("150.0") and exposure.numbers[0].unit == "INR crore"
    citation = exposure.citations[0]
    assert (citation.doc_id, citation.source) == ("REQ", "bank_input")
    assert exposure.added_by == "bank_input"


def test_merge_is_idempotent_and_drops_removed_parameters(tmp_path: Path) -> None:
    write_facts(tmp_path, _existing())
    both = _cfg(tmp_path, proposed_exposure=Decimal("150"), projected_turnover=Decimal("1100"))
    sync_bank_input_facts(tmp_path, both)
    first = (tmp_path / "verified_facts.json").read_text()
    sync_bank_input_facts(tmp_path, both)
    assert (tmp_path / "verified_facts.json").read_text() == first
    changed = _cfg(tmp_path, proposed_exposure=Decimal("200"))
    sync_bank_input_facts(tmp_path, changed)
    facts = read_all_facts(tmp_path)
    assert [f.fact_id for f in facts] == ["F001", "F007", "F008"]
    assert "INR 200 crore" in facts[-1].statement
    sync_bank_input_facts(tmp_path, _cfg(tmp_path))
    assert [f.fact_id for f in read_all_facts(tmp_path)] == ["F001", "F007"]


def test_no_parameters_leaves_the_file_untouched(tmp_path: Path) -> None:
    write_facts(tmp_path, _existing())
    before = (tmp_path / "verified_facts.json").read_text()
    sync_bank_input_facts(tmp_path, _cfg(tmp_path))
    assert (tmp_path / "verified_facts.json").read_text() == before
    assert json.loads(before)[0]["fact_id"] == "F001"
