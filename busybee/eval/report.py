"""Assemble all metric results into `EvalMetrics`, write metrics.json, and render a markdown table.

`write_eval_report` puts `metrics.json` and `metrics.md` under `<eval_root>/<run_id>/` using
atomic writes. `metrics_markdown` renders the headline numbers (ratios as percentages, missing
ones as n/a; with repeats, `mean (min, max, n)` for the LLM-judged ratios) followed by
a table of recall and precision for the main, main + appendix and all-facts sets, then
per-task call counts and stage timings.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from busybee.schema.io import write_model_atomic

from .metrics.citation_precision import CitationPrecisionResult
from .metrics.page_exact import PageExactResult
from .metrics.planted_errors import PlantedErrorResult
from .metrics.precision import PrecisionResult
from .metrics.proof_pass import ProofPassResult
from .metrics.recall import RecallResult
from .metrics.run_stats import RunStats
from .metrics.shown_subsets import SubsetScore


class RepeatStat(BaseModel):
    """One LLM-judged ratio across repeated judge runs."""

    values: list[float] = Field(default_factory=list)
    mean: float | None = None
    min: float | None = None
    max: float | None = None


def repeat_stat(values: list[float | None]) -> RepeatStat:
    """Summarise the defined values of repeated judge runs."""
    kept = [v for v in values if v is not None]
    if not kept:
        return RepeatStat()
    return RepeatStat(values=kept, mean=sum(kept) / len(kept), min=min(kept), max=max(kept))


class EvalMetrics(BaseModel):
    """Every metric computed for one run."""

    run_id: str
    company: str = ""
    bank_id: str = ""
    num_facts: int = 0
    recall: RecallResult | None = None
    precision: PrecisionResult | None = None
    citation: CitationPrecisionResult | None = None
    page_exact: PageExactResult | None = None
    planted: PlantedErrorResult | None = None
    proof: ProofPassResult | None = None
    stats: RunStats = Field(default_factory=RunStats)
    subsets: list[SubsetScore] = Field(default_factory=list)
    repeats: int = 1
    repeat_stats: dict[str, RepeatStat] = Field(default_factory=dict)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _judged(metrics: EvalMetrics, key: str, single: float | None) -> str:
    stat = metrics.repeat_stats.get(key)
    if metrics.repeats <= 1 or stat is None or stat.mean is None:
        return _pct(single)
    return (
        f"{_pct(stat.mean)} mean (min {_pct(stat.min)}, max {_pct(stat.max)}, n={len(stat.values)})"
    )


def metrics_markdown(metrics: EvalMetrics) -> str:
    """Render the metrics as a markdown document with tables."""
    recall, precision, citation = metrics.recall, metrics.precision, metrics.citation
    rows = [
        (
            "Important-statement recall",
            _judged(metrics, "recall", recall.recall if recall else None),
        ),
        (
            "Recall (must-have only)",
            _judged(metrics, "recall_must_have", recall.recall_must_have if recall else None),
        ),
        (
            "Important-statement precision",
            _judged(metrics, "precision", precision.precision if precision else None),
        ),
        (
            "Citation precision",
            _judged(
                metrics, "citation_precision", citation.citation_precision if citation else None
            ),
        ),
        ("Page-exact rate", _pct(metrics.page_exact.page_exact if metrics.page_exact else None)),
        ("Planted-error catch rate", _pct(metrics.planted.catch_rate if metrics.planted else None)),
        ("Proof pass rate", _pct(metrics.proof.proof_pass if metrics.proof else None)),
        ("Run time (s)", f"{metrics.stats.total_seconds:.1f}"),
        ("LLM calls", str(metrics.stats.total_calls)),
    ]
    lines = [
        f"# Evaluation: {metrics.company or metrics.run_id} (run {metrics.run_id})",
        "",
        f"Report facts: {metrics.num_facts}",
        *(
            [f"Judge repeats: {metrics.repeats} (headline cells are mean over repeats)"]
            if metrics.repeats > 1
            else []
        ),
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *(f"| {name} | {value} |" for name, value in rows),
    ]
    if metrics.subsets:
        lines += [
            "",
            "| Fact set | Facts | Recall | Recall (must-have) | Precision |",
            "| --- | --- | --- | --- | --- |",
            *(
                f"| {s.name} | {s.num_facts} | {_pct(s.recall)} | {_pct(s.recall_must_have)} "
                f"| {_pct(s.precision)} |"
                for s in metrics.subsets
            ),
        ]
    if metrics.stats.calls_per_task:
        lines += ["", "| LLM task | Calls |", "| --- | --- |"]
        lines += [f"| {task} | {count} |" for task, count in metrics.stats.calls_per_task.items()]
    if metrics.stats.stage_seconds:
        lines += ["", "| Stage | Seconds |", "| --- | --- |"]
        lines += [f"| {name} | {secs:.1f} |" for name, secs in metrics.stats.stage_seconds.items()]
    return "\n".join(lines) + "\n"


def write_eval_report(metrics: EvalMetrics, eval_root: str | Path) -> Path:
    """Write metrics.json and metrics.md under eval_root/<run_id>; return that directory."""
    target = Path(eval_root) / metrics.run_id
    write_model_atomic(target / "metrics.json", metrics)
    markdown_path = target / "metrics.md"
    temporary = markdown_path.with_suffix(".md.tmp")
    temporary.write_text(metrics_markdown(metrics), encoding="utf-8")
    temporary.replace(markdown_path)
    return target
