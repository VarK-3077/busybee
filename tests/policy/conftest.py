"""Fixtures: a binding mock provider for the example borrower and a run config."""

from pathlib import Path

import pytest
from policy_helpers import binding_json, example_facts, judge_replies

from busybee.llm import MockProvider
from busybee.schema.run import RunConfig


@pytest.fixture
def example_provider() -> MockProvider:
    facts = example_facts()
    return MockProvider(
        {"policy.bind_inputs": [binding_json(facts)], "policy.judge_slot": judge_replies(facts)}
    )


@pytest.fixture
def run_config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_id=f"test_policy_{tmp_path.name[-8:]}",
        docs_dir=tmp_path,
        bank_id="demo_bank",
        out_dir=tmp_path / "out",
        workspace_dir=tmp_path,
    )
