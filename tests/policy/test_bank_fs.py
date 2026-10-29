"""Bank folder loading and saving of machine-written formalisations."""

import json

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank, save_formalisation
from busybee.policy.parse_eval import parse_eval_output


def test_load_demo_bank() -> None:
    bank = load_bank(BANKS_DIR, "demo_bank")
    assert bank.name.startswith("Demo Bank of India")
    assert bank.version == "1.0"
    assert [spec.score_id for spec in bank.scores] == [
        "financial_strength_score",
        "internal_risk_grade",
        "maximum_exposure",
    ]
    assert bank.lean_path is not None and bank.lean_path.endswith("policy.lean")
    assert not bank.approval.approved


def test_save_formalisation_writes_unapproved_approval(tmp_path) -> None:
    save_formalisation(tmp_path / "bank", "def x : Int := 1", "mock-model")
    assert (tmp_path / "bank" / "policy.lean").read_text() == "def x : Int := 1\n"
    approval = json.loads((tmp_path / "bank" / "approval.json").read_text())
    assert approval["approved"] is False
    assert approval["generated_by"] == "mock-model"


def test_parse_eval_handles_score_ids_ending_in_grade() -> None:
    stdout = "internal_risk_grade=5\ninternal_risk_grade_grade=Acceptable risk\nnoise\n"
    parsed = parse_eval_output(stdout, ["internal_risk_grade", "other"])
    assert parsed["internal_risk_grade"].value == "5"
    assert parsed["internal_risk_grade"].grade == "Acceptable risk"
    assert "other" not in parsed
