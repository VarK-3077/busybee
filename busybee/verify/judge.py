"""Pluggable verification judges: the LLM, a small classifier sidecar, or both in tiers.

`Judge` is a protocol with `entailment` / `entailment_batch` (does the passage support the
statement? -> `Decision{label, prob}`) and `relevance` / `relevance_batch` (how related is a
statement to the policy slot descriptions, 0..1). Implementations:

* `LLMJudge` adapts `entailment.judge_entailment` and `relevance.judge_relevance` unchanged: a
  supported verdict is prob 1.0 with the model's verbatim quote, anything else prob 0.0.
* `ClassifierJudge` is an HTTP client for the sidecar in `tools/judge_sidecar/`: POST /entail
  `{pairs:[{statement, passage}]}` -> `{probs}` (HHEM consistency probability) and POST /rerank
  `{query, passages}` -> `{scores}` (bge reranker, sigmoid). Requests are batched (32), time out
  after `BUSYBEE_JUDGE_TIMEOUT_S` (default 60) and retry transport errors, 429 and 5xx with
  `busybee.llm.retry` inside a budget of `BUSYBEE_JUDGE_RETRY_BUDGET_S` (default 120). A label is
  `supported` at prob >= 0.5. Each classifier decision is appended to the audit log (llm_log.jsonl)
  with task `judge_entailment_classifier` and the prob so eval and profiling see it. Relevance
  scores each statement against every policy slot line separately and keeps the maximum.
* `TieredJudge(classifier, llm, low, high, accept_only)` asks the classifier first. In accept-only
  mode (default, `BUSYBEE_JUDGE_ACCEPT_ONLY=1`) the classifier decides only when prob >= high
  (supported, source `classifier`); everything else goes to the LLM (source `llm`, with its
  quote), because the benchmark showed low scores do not mean unsupported. With accept-only 0 the
  old symmetric mode applies: prob <= low or >= high is accepted as is, strictly inside the band
  goes to the LLM. Relevance is the classifier's.

`judge_from_env(provider)` picks one from `BUSYBEE_JUDGE=llm|classifier|tiered` (default llm);
`BUSYBEE_JUDGE_URL` (default http://127.0.0.1:8100) is the sidecar and `BUSYBEE_JUDGE_LOW` /
`BUSYBEE_JUDGE_HIGH` (0.35 / 0.80) bound the tier band.
"""

import asyncio
import json
import os
import time
from collections.abc import Sequence
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel

from busybee.llm import AuditEntry, Message, Role, record
from busybee.llm.provider import Provider
from busybee.llm.retry import UnreachableWatch, call_with_retry
from busybee.schema.facts import NotebookEntry

from .entailment import Verdict, judge_entailment
from .passage_window import window_around_numbers
from .relevance import judge_relevance

JUDGE_ENV = "BUSYBEE_JUDGE"
URL_ENV = "BUSYBEE_JUDGE_URL"
LOW_ENV = "BUSYBEE_JUDGE_LOW"
HIGH_ENV = "BUSYBEE_JUDGE_HIGH"
ACCEPT_ONLY_ENV = "BUSYBEE_JUDGE_ACCEPT_ONLY"
DEFAULT_URL = "http://127.0.0.1:8100"
DEFAULT_LOW = 0.35
DEFAULT_HIGH = 0.80
BATCH_SIZE = 32
SUPPORT_THRESHOLD = 0.5
CLASSIFIER_TASK = "judge_entailment_classifier"
MAX_SLOT_LINES = 40
MAX_SLOT_CHARS = 300


class Decision(BaseModel):
    """One entailment verdict: label, probability of support, who decided, optional LLM quote."""

    label: Literal["supported", "unsupported"]
    prob: float
    source: Literal["classifier", "llm"] = "classifier"
    quote: str = ""
    method: str = ""
    note: str = ""


class Judge(Protocol):
    """What verification needs from a judge."""

    async def entailment(self, statement: str, passage: str) -> Decision: ...

    async def entailment_batch(self, pairs: Sequence[tuple[str, str]]) -> list[Decision]: ...

    async def relevance(self, statement: str, context: str) -> float: ...

    async def relevance_batch(self, statements: Sequence[str], context: str) -> list[float]: ...


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


class LLMJudge:
    """The existing LLM judges behind the Judge interface."""

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    async def entailment(self, statement: str, passage: str) -> Decision:
        """Judge with the LLM; supported is prob 1.0 with its verbatim quote, else 0.0."""
        output = await judge_entailment(statement, passage, self.provider)
        supported = output.verdict is Verdict.supported
        return Decision(
            label="supported" if supported else "unsupported",
            prob=1.0 if supported else 0.0,
            source="llm",
            quote=output.quote,
            method=output.method,
            note=output.note,
        )

    async def entailment_batch(self, pairs: Sequence[tuple[str, str]]) -> list[Decision]:
        """Judge each pair with one LLM call, concurrently."""
        return list(await asyncio.gather(*(self.entailment(s, p) for s, p in pairs)))

    async def relevance(self, statement: str, context: str) -> float:
        """1.0 when the LLM keeps the statement, else 0.0."""
        return (await self.relevance_batch([statement], context))[0]

    async def relevance_batch(self, statements: Sequence[str], context: str) -> list[float]:
        """Keep/drop every statement with the batched LLM relevance filter."""
        entries = [
            NotebookEntry(entry_id=f"S{index}", statement=statement)
            for index, statement in enumerate(statements)
        ]
        decided = await judge_relevance(entries, "", self.provider, required_inputs=context)
        return [1.0 if decided[entry.entry_id].keep else 0.0 for entry in entries]


class ClassifierJudge:
    """HTTP client for the judge sidecar (HHEM entailment, bge reranker relevance)."""

    def __init__(
        self,
        url: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float | None = None,
        retry_budget_s: float | None = None,
    ) -> None:
        self.url = (url or os.environ.get(URL_ENV) or DEFAULT_URL).rstrip("/")
        self.transport = transport
        self._watch = UnreachableWatch(self.url)
        self.timeout_s = timeout_s or _env_float("BUSYBEE_JUDGE_TIMEOUT_S", 60.0)
        self.retry_budget_s = (
            retry_budget_s
            if retry_budget_s is not None
            else _env_float("BUSYBEE_JUDGE_RETRY_BUDGET_S", 120.0)
        )

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, list[float]]:
        async def attempt() -> dict[str, list[float]]:
            async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s) as http:
                response = await http.post(f"{self.url}{path}", json=payload)
                response.raise_for_status()
                return response.json()

        async def watched() -> dict[str, list[float]]:
            try:
                body = await attempt()
            except Exception as error:
                self._watch.failed(error)
                raise
            self._watch.succeeded()
            return body

        return await call_with_retry(watched, budget_s=self.retry_budget_s)

    async def entailment(self, statement: str, passage: str) -> Decision:
        """Classify one pair."""
        return (await self.entailment_batch([(statement, passage)]))[0]

    async def entailment_batch(self, pairs: Sequence[tuple[str, str]]) -> list[Decision]:
        """Classify pairs in requests of at most 32; one Decision per pair, in order."""
        decisions: list[Decision] = []
        for start in range(0, len(pairs), BATCH_SIZE):
            part = pairs[start : start + BATCH_SIZE]
            began = time.monotonic()
            body = await self._post(
                "/entail",
                {
                    "pairs": [
                        {"statement": s, "passage": window_around_numbers(p, s)} for s, p in part
                    ]
                },
            )
            probs = body["probs"]
            if len(probs) != len(part):
                raise ValueError(f"judge sidecar returned {len(probs)} probs for {len(part)} pairs")
            latency = (time.monotonic() - began) / max(1, len(part))
            for (statement, passage), prob in zip(part, probs, strict=True):
                decision = Decision(
                    label="supported" if prob >= SUPPORT_THRESHOLD else "unsupported",
                    prob=float(prob),
                )
                await self._audit(
                    statement, window_around_numbers(passage, statement), decision, latency
                )
                decisions.append(decision)
        return decisions

    async def _audit(
        self, statement: str, passage: str, decision: Decision, latency_s: float
    ) -> None:
        await record(
            AuditEntry(
                task=CLASSIFIER_TASK,
                model=self.url,
                messages=[
                    Message(
                        role=Role.user,
                        content=f"Statement:\n{statement}\n\nSource passage:\n{passage}",
                    )
                ],
                text=json.dumps({"label": decision.label, "prob": decision.prob}),
                latency_s=latency_s,
            )
        )

    async def relevance(self, statement: str, context: str) -> float:
        """Relevance of one statement to the slot lines in context."""
        return (await self.relevance_batch([statement], context))[0]

    async def relevance_batch(self, statements: Sequence[str], context: str) -> list[float]:
        """Max reranker score of each statement over the context's slot lines (0..1)."""
        slots = [line.strip()[:MAX_SLOT_CHARS] for line in context.splitlines() if line.strip()]
        scores = [0.0] * len(statements)
        for slot in slots[:MAX_SLOT_LINES]:
            for start in range(0, len(statements), BATCH_SIZE):
                part = list(statements[start : start + BATCH_SIZE])
                body = await self._post("/rerank", {"query": slot, "passages": part})
                for offset, score in enumerate(body["scores"]):
                    scores[start + offset] = max(scores[start + offset], float(score))
        return scores


class TieredJudge:
    """Classifier first; the LLM only when the probability falls inside (low, high)."""

    def __init__(
        self,
        classifier: Judge,
        llm: Judge,
        low: float = DEFAULT_LOW,
        high: float = DEFAULT_HIGH,
        accept_only: bool = True,
    ) -> None:
        self.classifier = classifier
        self.llm = llm
        self.low = low
        self.high = high
        self.accept_only = accept_only

    def _in_band(self, decision: Decision) -> bool:
        if self.accept_only:
            return decision.prob < self.high
        return self.low < decision.prob < self.high

    async def entailment(self, statement: str, passage: str) -> Decision:
        """Accept-only: classifier at prob >= high, else LLM (symmetric: LLM inside the band)."""
        return (await self.entailment_batch([(statement, passage)]))[0]

    async def entailment_batch(self, pairs: Sequence[tuple[str, str]]) -> list[Decision]:
        """Classify all pairs in batch, then send only the in-band ones to the LLM."""
        decisions = await self.classifier.entailment_batch(pairs)
        uncertain = [i for i, d in enumerate(decisions) if self._in_band(d)]
        resolved = await asyncio.gather(*(self.llm.entailment(*pairs[i]) for i in uncertain))
        for index, decision in zip(uncertain, resolved, strict=True):
            decisions[index] = decision.model_copy(
                update={
                    "note": f"classifier prob {decisions[index].prob:.2f} not accepted; LLM judged"
                }
            )
        return decisions

    async def relevance(self, statement: str, context: str) -> float:
        """The classifier's relevance."""
        return await self.classifier.relevance(statement, context)

    async def relevance_batch(self, statements: Sequence[str], context: str) -> list[float]:
        """The classifier's relevance for every statement."""
        return await self.classifier.relevance_batch(statements, context)


def judge_from_env(
    provider: Provider, *, transport: httpx.AsyncBaseTransport | None = None
) -> Judge:
    """Build the judge named by BUSYBEE_JUDGE (llm | classifier | tiered; default llm)."""
    mode = (os.environ.get(JUDGE_ENV) or "llm").strip().lower()
    if mode == "llm":
        return LLMJudge(provider)
    classifier = ClassifierJudge(transport=transport)
    if mode == "classifier":
        return classifier
    if mode == "tiered":
        return TieredJudge(
            classifier,
            LLMJudge(provider),
            _env_float(LOW_ENV, DEFAULT_LOW),
            _env_float(HIGH_ENV, DEFAULT_HIGH),
            os.environ.get(ACCEPT_ONLY_ENV, "1").strip().lower() not in {"0", "false", "no", "off"},
        )
    raise ValueError(f"unknown {JUDGE_ENV}: {mode!r} (expected llm, classifier or tiered)")
