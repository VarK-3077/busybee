"""Run statistics: stage timings from stages.json and call counts per task from llm_log.jsonl.

`stages.json` is either a list of stage-status records or a mapping of name to record; timing
is `finished_at - started_at` for stages that have both. The LLM log counts every provider
attempt (retries included) per task tag and sums token usage.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from busybee.llm.audit_log import AuditEntry
from busybee.schema.io import read_json, read_jsonl


class RunStats(BaseModel):
    """Timings and call counts of one run."""

    stage_seconds: dict[str, float] = Field(default_factory=dict)
    total_seconds: float = 0.0
    calls_per_task: dict[str, int] = Field(default_factory=dict)
    total_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def _seconds(started: Any, finished: Any) -> float | None:
    if not started or not finished:
        return None
    try:
        return (
            datetime.fromisoformat(str(finished)) - datetime.fromisoformat(str(started))
        ).total_seconds()
    except ValueError:
        return None


def stage_timings(stages_path: Path) -> dict[str, float]:
    """Read stages.json into stage name to elapsed seconds."""
    if not stages_path.exists():
        return {}
    raw = read_json(stages_path)
    records = (
        [{"name": name, **value} for name, value in raw.items() if isinstance(value, dict)]
        if isinstance(raw, dict)
        else raw
    )
    timings: dict[str, float] = {}
    for record in records:
        elapsed = _seconds(record.get("started_at"), record.get("finished_at"))
        if elapsed is not None:
            timings[str(record.get("name", ""))] = max(elapsed, 0.0)
    return timings


def compute_run_stats(workspace_dir: str | Path) -> RunStats:
    """Return stage timings and per-task LLM call counts for a run workspace."""
    root = Path(workspace_dir)
    timings = stage_timings(root / "stages.json")
    entries = read_jsonl(root / "llm_log.jsonl", AuditEntry)
    per_task: dict[str, int] = {}
    for entry in entries:
        per_task[entry.task] = per_task.get(entry.task, 0) + 1
    return RunStats(
        stage_seconds=timings,
        total_seconds=sum(timings.values()),
        calls_per_task=dict(sorted(per_task.items())),
        total_calls=len(entries),
        input_tokens=sum(e.usage.input_tokens for e in entries),
        output_tokens=sum(e.usage.output_tokens for e in entries),
    )
