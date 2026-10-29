"""Verify tests default to the per-entry entailment path; passage-batch tests opt in explicitly."""

import pytest


@pytest.fixture(autouse=True)
def per_entry_entailment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_VERIFY_BATCH", "entry")
