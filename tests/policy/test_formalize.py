"""The write -> compile -> check -> repair loop with a mock provider and the real compiler."""

import json

import pytest
from policy_helpers import BANKS_DIR

from busybee.lean.toolchain import find_lake, find_lean
from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.formalize.loop import formalise
from busybee.policy.formalize.writer import writer_messages

pytestmark = pytest.mark.skipif(
    find_lean() is None or find_lake() is None, reason="Lean toolchain is not installed"
)

BAD = "import BusyBee.Common\n\ndef broken : Int := missingThing\n"


def _good() -> str:
    return (BANKS_DIR / "demo_bank" / "policy.lean").read_text(encoding="utf-8")


def _write(source: str) -> str:
    return json.dumps({"lean_source": source})


async def test_bad_file_then_good_file(tmp_path) -> None:
    provider = MockProvider(
        {
            "policy.formalize_write": [_write(BAD), _write(_good())],
            "policy.formalize_check": [json.dumps({"ok": True, "issues": []})],
        }
    )
    bank = load_bank(BANKS_DIR, "demo_bank")
    result = await formalise(provider, bank, tmp_path)
    assert result.ok
    assert result.source == _good()
    tasks = [call["task"] for call in provider.calls]
    assert tasks == ["policy.formalize_write", "policy.formalize_write", "policy.formalize_check"]
    repair_prompt = provider.calls[1]["messages"][-1].content
    assert "missingThing" in repair_prompt
    assert "round 1: compiled=False" in result.log[0]


async def test_checker_issues_are_fed_back(tmp_path) -> None:
    provider = MockProvider(
        {
            "policy.formalize_write": [_write(_good())],
            "policy.formalize_check": [
                json.dumps({"ok": False, "issues": ["Strong band should start at 80"]}),
                json.dumps({"ok": True, "issues": []}),
            ],
        }
    )
    bank = load_bank(BANKS_DIR, "demo_bank")
    result = await formalise(provider, bank, tmp_path)
    assert result.ok
    assert "Strong band should start at 80" in provider.calls[2]["messages"][-1].content


async def test_gives_up_after_max_rounds_with_best_source(tmp_path) -> None:
    provider = MockProvider({"policy.formalize_write": [_write(BAD)]})
    bank = load_bank(BANKS_DIR, "demo_bank")
    result = await formalise(provider, bank, tmp_path, max_rounds=2)
    assert not result.ok
    assert result.source == BAD
    assert len(provider.calls) == 2


def test_writer_prompt_has_conventions_and_example() -> None:
    bank = load_bank(BANKS_DIR, "demo_bank")
    prompt = "\n".join(m.content for m in writer_messages(bank))
    assert "Lean 4 core only, no Mathlib" in prompt
    assert "namespace BusyBee.Example" in prompt
    assert "financial_strength_score_grade" in prompt
    assert "namespace BusyBee.Policy.DemoBank" in prompt
