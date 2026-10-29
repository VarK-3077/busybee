"""Tests for audit timings, LLM call counts, models, policy version, and toolchain."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from busybee.compose.audit import (
    build_audit_block,
    load_stage_statuses,
    stage_timings,
    summarize_llm_log,
)
from busybee.compose.inputs import load_bank_policy
from busybee.schema.io import write_models_atomic
from busybee.schema.run import StageState, StageStatus


def test_summarize_llm_log_counts_tasks_and_models(tmp_path: Path) -> None:
    path = tmp_path / "llm_log.jsonl"
    entries = [
        {"task": "extract", "model": "model-a"},
        {"task": "verify", "model": "model-b"},
        {"task": "verify", "model": "model-c"},
    ]
    path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )

    summary = summarize_llm_log(path)

    assert summary.calls == 3
    assert summary.by_task == {"extract": 1, "verify": 2}
    assert summary.by_model == {"model-a": 1, "model-b": 1, "model-c": 1}
    assert summary.models_by_task == {"extract": "model-a", "verify": "model-c"}


def test_stage_timings_use_start_and_finish(tmp_path: Path) -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    statuses = [
        StageStatus(
            name="extract",
            state=StageState.done,
            started_at=started,
            finished_at=started + timedelta(seconds=10),
        ),
        StageStatus(
            name="verify",
            state=StageState.done,
            started_at=started,
            finished_at=started + timedelta(seconds=2.5),
        ),
        StageStatus(name="compose", state=StageState.pending),
    ]
    write_models_atomic(tmp_path / "stages.json", statuses)

    loaded = load_stage_statuses(tmp_path)

    assert loaded == statuses
    assert stage_timings(loaded) == {"extract": 10.0, "verify": 2.5}


def test_build_audit_block_combines_all_sources(tmp_path: Path, banks_dir: Path) -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    write_models_atomic(
        tmp_path / "stages.json",
        [
            StageStatus(
                name="extract",
                state=StageState.done,
                started_at=started,
                finished_at=started + timedelta(seconds=4),
            )
        ],
    )
    (tmp_path / "llm_log.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"task": "extract", "model": "model-a"}),
                json.dumps({"task": "compose", "model": "model-b"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    policy = load_bank_policy(banks_dir, "demo_bank")

    audit = build_audit_block(
        tmp_path,
        policy,
        stage_models={"compose": "configured-model"},
        lean_version="Lean 4.13.0",
    )

    assert audit.llm_calls == 2
    assert audit.models == {"compose": "model-b", "extract": "model-a"}
    assert audit.stage_timings == {"extract": 4.0}
    assert audit.policy_version == "2.3"
    assert audit.lean_toolchain == "Lean 4.13.0"
    assert audit.generated_at is not None


def test_build_audit_block_tolerates_missing_workspace_files(
    tmp_path: Path,
    banks_dir: Path,
) -> None:
    policy = load_bank_policy(banks_dir, "demo_bank")

    audit = build_audit_block(tmp_path, policy, lean_version="")

    assert audit.llm_calls == 0
    assert audit.models == {}
    assert audit.stage_timings == {}
    assert audit.lean_toolchain == ""
