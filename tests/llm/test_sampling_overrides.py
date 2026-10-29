"""BUSYBEE_LLM_SAMPLING splits into standard request fields and vLLM extra_body."""

from busybee.llm.openai_compatible import sampling_overrides


def test_unset_gives_nothing(monkeypatch):
    monkeypatch.delenv("BUSYBEE_LLM_SAMPLING", raising=False)
    assert sampling_overrides() == {}


def test_split_standard_and_extra(monkeypatch):
    monkeypatch.setenv(
        "BUSYBEE_LLM_SAMPLING", '{"temperature": 0.6, "top_p": 0.95, "repetition_penalty": 1.05}'
    )
    assert sampling_overrides() == {
        "temperature": 0.6,
        "top_p": 0.95,
        "extra_body": {"repetition_penalty": 1.05},
    }
