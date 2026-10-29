"""Recall and precision restricted to the facts a reader sees: main section, main + appendix, all.

The LLM judge runs once over every report fact (`compute_recall`, `compute_precision`); this
module only filters those results, so the three views cost no extra LLM calls. A gold fact
counts as recalled in a subset when at least one fact the judge matched to it is in the subset;
precision of a subset is the share of its facts the judge found important and correct. The
subsets come from `shown_facts.json` written by render (`main`, `appendix` fact id lists);
without it only the "all" view is produced.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel

from busybee.eval.gold import GoldFact
from busybee.schema.io import read_json

from .common import ratio
from .precision import PrecisionResult
from .recall import RecallResult

SHOWN_FACTS_RELATIVE = Path("out") / "data" / "shown_facts.json"


class SubsetScore(BaseModel):
    """Recall and precision of one fact subset."""

    name: str
    num_facts: int = 0
    recall: float | None = None
    recall_must_have: float | None = None
    precision: float | None = None


def load_shown_sets(path: str | Path | None) -> dict[str, set[str]]:
    """The main and appendix fact-id sets from shown_facts.json, empty when it is missing."""
    if path is None or not Path(path).exists():
        return {}
    raw = read_json(path)
    return {key: set(raw.get(key, [])) for key in ("main", "appendix")}


def subset_score(
    name: str,
    ids: set[str],
    gold_facts: Sequence[GoldFact],
    recall: RecallResult,
    precision: PrecisionResult,
    all_ids: Sequence[str],
) -> SubsetScore:
    """Filter the all-facts judgements down to the facts in `ids`."""
    hits = [
        bool(ids.intersection(recall.matched_fact_ids.get(gold.statement, [])))
        for gold in gold_facts
    ]
    must = [hit for hit, gold in zip(hits, gold_facts, strict=True) if gold.must_have]
    bad = set(precision.unimportant) | set(precision.incorrect)
    kept = [fact_id for fact_id in all_ids if fact_id in ids]
    return SubsetScore(
        name=name,
        num_facts=len(kept),
        recall=ratio(sum(hits), len(hits)),
        recall_must_have=ratio(sum(must), len(must)),
        precision=ratio(sum(1 for fact_id in kept if fact_id not in bad), len(kept)),
    )


def subset_scores(
    shown: Mapping[str, set[str]],
    gold_facts: Sequence[GoldFact],
    recall: RecallResult,
    precision: PrecisionResult,
    all_ids: Sequence[str],
) -> list[SubsetScore]:
    """Scores for main, main + appendix and all facts (only "all" when nothing was rendered)."""
    everything = set(all_ids)
    views = (
        [
            ("main", shown["main"] & everything),
            ("main + appendix", (shown["main"] | shown["appendix"]) & everything),
        ]
        if shown
        else []
    )
    views.append(("all facts", everything))
    return [subset_score(n, ids, gold_facts, recall, precision, all_ids) for n, ids in views]
