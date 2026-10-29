"""Build the audit block from stage statuses, the LLM log, bank policy, and Lean."""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from busybee.lean.toolchain import toolchain_version
from busybee.schema.io import read_models
from busybee.schema.policy import BankPolicy
from busybee.schema.report import AuditBlock
from busybee.schema.run import StageStatus


@dataclass(frozen=True)
class LLMLogSummary:
    """Call counts and observed models from llm_log.jsonl."""

    calls: int = 0
    by_task: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, int] = field(default_factory=dict)
    models_by_task: dict[str, str] = field(default_factory=dict)


def load_stage_statuses(workspace_dir: str | Path) -> list[StageStatus]:
    """Read stages.json, returning an empty list when it does not exist yet."""
    path = Path(workspace_dir) / "stages.json"
    return read_models(path, StageStatus) if path.exists() else []


def stage_timings(statuses: list[StageStatus]) -> dict[str, float]:
    """Return completed stage durations in seconds, keyed by stage name."""
    timings: dict[str, float] = {}
    for status in statuses:
        if status.started_at is None or status.finished_at is None:
            continue
        seconds = (status.finished_at - status.started_at).total_seconds()
        timings[status.name] = max(seconds, 0.0)
    return timings


def summarize_llm_log(path: str | Path) -> LLMLogSummary:
    """Count calls per task and model in an append-only llm_log.jsonl file."""
    target = Path(path)
    if not target.exists():
        return LLMLogSummary()
    by_task: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    models_by_task: dict[str, str] = {}
    calls = 0
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        calls += 1
        task = str(entry.get("task") or "unknown")
        model = str(entry.get("model") or "unknown")
        by_task[task] += 1
        by_model[model] += 1
        models_by_task[task] = model
    return LLMLogSummary(
        calls=calls,
        by_task=dict(by_task),
        by_model=dict(by_model),
        models_by_task=models_by_task,
    )


def build_audit_block(
    workspace_dir: str | Path,
    policy: BankPolicy,
    *,
    stage_models: dict[str, str] | None = None,
    generated_at: datetime | None = None,
    lean_version: str | None = None,
) -> AuditBlock:
    """Assemble provenance for the report from workspace files and the toolchain."""
    workspace = Path(workspace_dir)
    log = summarize_llm_log(workspace / "llm_log.jsonl")
    models = dict(stage_models or {})
    models.update(log.models_by_task)
    return AuditBlock(
        models=models,
        stage_timings=stage_timings(load_stage_statuses(workspace)),
        llm_calls=log.calls,
        policy_version=policy.version,
        lean_toolchain=toolchain_version() if lean_version is None else lean_version,
        generated_at=generated_at or datetime.now(UTC),
    )
