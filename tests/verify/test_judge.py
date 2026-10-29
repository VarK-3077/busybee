"""Judge implementations: classifier over a fake HTTP transport, tiered band logic, env switch."""

import json
from collections.abc import Callable, Sequence

import httpx
import pytest

from busybee.llm import configure_audit_log
from busybee.verify.judge import (
    ClassifierJudge,
    Decision,
    LLMJudge,
    TieredJudge,
    judge_from_env,
)

from .helpers import judge_provider


def sidecar(
    prob_of: Callable[[str, str], float] = lambda s, p: 0.9,
    calls: list[tuple[str, dict]] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if calls is not None:
            calls.append((request.url.path, body))
        if request.url.path == "/entail":
            return httpx.Response(
                200, json={"probs": [prob_of(x["statement"], x["passage"]) for x in body["pairs"]]}
            )
        return httpx.Response(
            200,
            json={
                "scores": [
                    0.9 if body["query"].split(": ")[-1].lower() in p.lower() else 0.05
                    for p in body["passages"]
                ]
            },
        )

    return httpx.MockTransport(handler)


class FixedJudge:
    """Judge stub with a prob per statement; counts calls."""

    def __init__(self, probs: Sequence[float], source: str = "classifier") -> None:
        self.probs, self.source, self.calls = list(probs), source, 0

    async def entailment(self, statement: str, passage: str) -> Decision:
        return (await self.entailment_batch([(statement, passage)]))[0]

    async def entailment_batch(self, pairs: Sequence[tuple[str, str]]) -> list[Decision]:
        self.calls += len(pairs)
        return [
            Decision(
                label="supported" if p >= 0.5 else "unsupported",
                prob=p,
                source=self.source,
                quote="q" if self.source == "llm" else "",
            )
            for _, p in zip(pairs, self.probs, strict=False)
        ]

    async def relevance(self, statement: str, context: str) -> float:
        return 1.0

    async def relevance_batch(self, statements: Sequence[str], context: str) -> list[float]:
        return [1.0] * len(statements)


async def test_classifier_batches_and_labels(tmp_path) -> None:  # noqa: ANN001
    calls: list[tuple[str, dict]] = []
    log = tmp_path / "llm_log.jsonl"
    configure_audit_log(log)
    judge = ClassifierJudge(
        "http://sidecar", transport=sidecar(lambda s, p: 0.2 if "no" in s else 0.9, calls)
    )
    pairs = [("yes", "p")] * 40 + [("no", "p")]
    decisions = await judge.entailment_batch(pairs)
    configure_audit_log(None)
    assert [len(body["pairs"]) for _, body in calls] == [32, 9]
    assert decisions[0].label == "supported" and decisions[0].source == "classifier"
    assert decisions[-1].label == "unsupported" and decisions[-1].prob == pytest.approx(0.2)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(rows) == 41
    assert rows[-1]["task"] == "judge_entailment_classifier"
    assert json.loads(rows[-1]["text"])["prob"] == pytest.approx(0.2)


async def test_classifier_retries_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"probs": [0.7]})

    judge = ClassifierJudge("http://sidecar", transport=httpx.MockTransport(handler))
    judge.retry_budget_s = 30
    monkeypatch.setattr("busybee.llm.retry._sleep", lambda seconds: _noop())
    assert (await judge.entailment("s", "p")).prob == pytest.approx(0.7)
    assert len(attempts) == 2


async def _noop() -> None:
    return None


async def test_relevance_takes_max_over_slot_lines() -> None:
    judge = ClassifierJudge("http://sidecar", transport=sidecar())
    context = "- revenue: sales\n- dscr: coverage"
    scores = await judge.relevance_batch(["sales rose", "weather"], context)
    assert scores == [0.9, 0.05]
    assert await judge.relevance("coverage fine", context) == 0.9


@pytest.mark.parametrize(
    ("prob", "expect_llm", "label"),
    [
        (0.95, False, "supported"),
        (0.80, False, "supported"),
        (0.10, False, "unsupported"),
        (0.35, False, "unsupported"),
        (0.5, True, "supported"),
    ],
)
async def test_tiered_band(prob: float, expect_llm: bool, label: str) -> None:
    llm = FixedJudge([1.0], source="llm")
    judge = TieredJudge(FixedJudge([prob]), llm, low=0.35, high=0.80, accept_only=False)
    decision = await judge.entailment("s", "p")
    assert (llm.calls == 1) is expect_llm
    assert decision.label == label
    assert decision.source == ("llm" if expect_llm else "classifier")


@pytest.mark.parametrize(
    ("prob", "expect_llm"), [(0.95, False), (0.80, False), (0.79, True), (0.5, True), (0.02, True)]
)
async def test_tiered_accept_only(prob: float, expect_llm: bool) -> None:
    llm = FixedJudge([0.0], source="llm")
    judge = TieredJudge(FixedJudge([prob]), llm)
    assert judge.accept_only
    decision = await judge.entailment("s", "p")
    assert (llm.calls == 1) is expect_llm
    assert decision.source == ("llm" if expect_llm else "classifier")
    if not expect_llm:
        assert decision.label == "supported"


async def test_classifier_sends_windowed_passage() -> None:
    calls: list[tuple[str, dict]] = []
    judge = ClassifierJudge("http://box", transport=sidecar(calls=calls))
    passage = "x" * 5000 + " Revenue 1,845.32 crore " + "y" * 5000
    await judge.entailment("Revenue was 1,845.32 crore", passage)
    sent = calls[0][1]["pairs"][0]
    assert len(sent["passage"]) <= 1500 and "1,845.32" in sent["passage"]
    assert sent["statement"] == "Revenue was 1,845.32 crore"


async def test_tiered_batch_sends_only_band_to_llm() -> None:
    llm = FixedJudge([0.0], source="llm")
    judge = TieredJudge(FixedJudge([0.9, 0.5, 0.1]), llm, accept_only=False)
    decisions = await judge.entailment_batch([("a", "p"), ("b", "p"), ("c", "p")])
    assert [d.source for d in decisions] == ["classifier", "llm", "classifier"]
    assert llm.calls == 1


async def test_llm_judge_adapts_existing_judge() -> None:
    judge = LLMJudge(judge_provider(supports=lambda s, p: s in p))
    ok = await judge.entailment("Revenue 5", "Revenue 5 crore")
    bad = await judge.entailment("Debt 9", "Revenue 5 crore")
    assert (ok.label, ok.prob, ok.source) == ("supported", 1.0, "llm")
    assert ok.quote and bad.label == "unsupported"


def test_judge_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = judge_provider()
    monkeypatch.delenv("BUSYBEE_JUDGE", raising=False)
    assert isinstance(judge_from_env(provider), LLMJudge)
    monkeypatch.setenv("BUSYBEE_JUDGE", "classifier")
    monkeypatch.setenv("BUSYBEE_JUDGE_URL", "http://box:9/")
    judge = judge_from_env(provider)
    assert isinstance(judge, ClassifierJudge) and judge.url == "http://box:9"
    monkeypatch.setenv("BUSYBEE_JUDGE", "tiered")
    monkeypatch.setenv("BUSYBEE_JUDGE_LOW", "0.2")
    monkeypatch.setenv("BUSYBEE_JUDGE_HIGH", "0.9")
    tiered = judge_from_env(provider)
    assert isinstance(tiered, TieredJudge) and (tiered.low, tiered.high) == (0.2, 0.9)
    assert tiered.accept_only
    monkeypatch.setenv("BUSYBEE_JUDGE_ACCEPT_ONLY", "0")
    symmetric = judge_from_env(provider)
    assert isinstance(symmetric, TieredJudge) and not symmetric.accept_only
    monkeypatch.setenv("BUSYBEE_JUDGE", "nope")
    with pytest.raises(ValueError):
        judge_from_env(provider)
