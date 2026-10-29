"""Workspace paths, run configuration defaults and the stages.json record."""

from pathlib import Path

from busybee.orchestrate.config import build_run_config, default_run_id
from busybee.orchestrate.status import mark_done, mark_failed, mark_running, read_statuses
from busybee.orchestrate.workspace import Workspace
from busybee.schema.run import ExtractMode, StageState


def test_workspace_paths_live_under_the_run_directory(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path, "run1")
    assert workspace.run_dir == tmp_path / "run1"
    for path in (
        workspace.documents,
        workspace.index_dir,
        workspace.notebook,
        workspace.verified_facts,
        workspace.dropped,
        workspace.scores,
        workspace.inferences,
        workspace.concerns,
        workspace.report,
        workspace.llm_log,
        workspace.stages,
        workspace.out_dir,
        workspace.lean_dir,
    ):
        assert workspace.run_dir in path.parents


def test_config_defaults_and_env_overrides(tmp_path: Path) -> None:
    cfg = build_run_config(tmp_path / "Acme Docs", "bank", tmp_path / "o", env={})
    assert cfg.window_tokens == 12000
    assert cfg.notebook_budget_tokens == 16000
    assert cfg.concurrency == 12
    assert cfg.extract_mode is ExtractMode.segmented
    assert cfg.segment_min_windows == 2
    assert cfg.run_id == default_run_id(tmp_path / "Acme Docs") == "Acme-Docs"
    assert cfg.workspace_dir.name == cfg.run_id

    tuned = build_run_config(
        tmp_path,
        "bank",
        tmp_path / "o",
        env={
            "BUSYBEE_CONCURRENCY": "9",
            "BUSYBEE_EXTRACT_MODE": "global",
            "BUSYBEE_SEGMENT_MIN_WINDOWS": "3",
        },
    )
    assert tuned.concurrency == 9
    assert tuned.extract_mode is ExtractMode.global_
    assert tuned.segment_min_windows == 3


def test_status_transitions_are_persisted(tmp_path: Path) -> None:
    path = tmp_path / "stages.json"
    assert read_statuses(path) == {}
    mark_running(path, "ingest")
    assert read_statuses(path)["ingest"].state is StageState.running
    mark_done(path, "ingest")
    done = read_statuses(path)["ingest"]
    assert done.state is StageState.done and done.finished_at is not None
    mark_failed(path, "index", "bad")
    assert read_statuses(path)["index"].error == "bad"


def test_bank_inputs_come_from_arguments_then_environment(tmp_path: Path) -> None:
    from decimal import Decimal

    import pytest

    plain = build_run_config(tmp_path, "bank", tmp_path / "o", env={})
    assert plain.proposed_exposure is None and plain.projected_turnover is None
    env = {"BUSYBEE_PROPOSED_EXPOSURE": "150", "BUSYBEE_PROJECTED_TURNOVER": "1,100.5"}
    from_env = build_run_config(tmp_path, "bank", tmp_path / "o", env=env)
    assert from_env.proposed_exposure == Decimal("150")
    assert from_env.projected_turnover == Decimal("1100.5")
    given = build_run_config(tmp_path, "bank", tmp_path / "o", proposed_exposure="90", env=env)
    assert given.proposed_exposure == Decimal("90")
    with pytest.raises(ValueError, match="positive"):
        build_run_config(tmp_path, "bank", tmp_path / "o", proposed_exposure="-3", env={})
    with pytest.raises(ValueError, match="number"):
        build_run_config(tmp_path, "bank", tmp_path / "o", projected_turnover="lots", env={})


def test_extract_concurrency_default_and_env(tmp_path: Path) -> None:
    default = build_run_config(tmp_path / "d", "bank", tmp_path / "o", env={})
    assert default.extract_concurrency == 12
    assert default.concurrency == 12
    cfg = build_run_config(
        tmp_path / "d", "bank", tmp_path / "o", env={"BUSYBEE_EXTRACT_CONCURRENCY": "3"}
    )
    assert cfg.extract_concurrency == 3
    assert cfg.concurrency == 12
