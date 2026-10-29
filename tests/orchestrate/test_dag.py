"""The DAG runner: ordering, concurrency, failure isolation and resume, with toy stages."""

import asyncio
from pathlib import Path

import pytest

from busybee.orchestrate.config import build_run_config
from busybee.orchestrate.dag import PipelineError, run_dag
from busybee.orchestrate.stages import STAGES, RunContext, Stage, stage_names
from busybee.orchestrate.status import read_statuses
from busybee.orchestrate.workspace import Workspace
from busybee.schema.run import StageState


def make_context(tmp_path: Path) -> RunContext:
    cfg = build_run_config(tmp_path, "bank", tmp_path / "out", run_id="r", workspace_root=tmp_path)
    workspace = Workspace(tmp_path, "r")
    workspace.ensure()
    return RunContext(cfg=cfg, workspace=workspace, banks_dir=tmp_path)


def toy(name: str, deps: tuple[str, ...], events: list[str], fail: bool = False) -> Stage:
    async def run(ctx: RunContext) -> None:
        events.append(f"start:{name}")
        await asyncio.sleep(0.01)
        if fail:
            raise RuntimeError("boom")
        (ctx.workspace.run_dir / f"{name}.txt").write_text("x")
        events.append(f"end:{name}")

    return Stage(name, deps, run, lambda c: [c.workspace.run_dir / f"{name}.txt"])


def test_registry_matches_architecture_dag() -> None:
    deps = {stage.name: set(stage.dependencies) for stage in STAGES}
    assert deps == {
        "ingest": set(),
        "index": {"ingest"},
        "extract": {"ingest"},
        "verify": {"extract", "index"},
        "scores": {"verify"},
        "infer": {"verify"},
        "adversary": {"scores", "infer"},
        "compose": {"adversary"},
        "render": {"compose"},
    }
    assert stage_names()[0] == "ingest"


async def test_independent_stages_run_concurrently(tmp_path: Path) -> None:
    events: list[str] = []
    stages = [toy("a", (), events), toy("b", ("a",), events), toy("c", ("a",), events)]
    await run_dag(make_context(tmp_path), stages=stages)
    assert events.index("end:a") < events.index("start:b")
    assert events.index("start:c") < events.index("end:b")


async def test_failure_blocks_dependants_but_not_independents(tmp_path: Path) -> None:
    events: list[str] = []
    stages = [
        toy("a", (), events),
        toy("bad", ("a",), events, fail=True),
        toy("after", ("bad",), events),
        toy("side", ("a",), events),
    ]
    ctx = make_context(tmp_path)
    with pytest.raises(PipelineError) as raised:
        await run_dag(ctx, stages=stages)
    assert set(raised.value.errors) == {"bad"}
    statuses = read_statuses(ctx.workspace.stages)
    assert statuses["bad"].state is StageState.failed
    assert statuses["side"].state is StageState.done
    assert "after" not in statuses


async def test_resume_skips_done_and_reruns_missing_output_with_dependants(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    stages = [toy("a", (), events), toy("b", ("a",), events), toy("c", ("b",), events)]
    ctx = make_context(tmp_path)
    await run_dag(ctx, stages=stages)
    events.clear()
    (ctx.workspace.run_dir / "b.txt").unlink()
    await run_dag(ctx, resume=True, stages=stages)
    assert events == ["start:b", "end:b", "start:c", "end:c"]


async def test_resume_reruns_running_stage_and_keeps_progress_but_fresh_run_clears_it(
    tmp_path: Path,
) -> None:
    from busybee.orchestrate.status import mark_running

    events: list[str] = []
    ctx = make_context(tmp_path)
    stages = [toy("a", (), events), toy("b", ("a",), events)]
    await run_dag(ctx, stages=stages)
    mark_running(ctx.workspace.stages, "b")
    (ctx.workspace.run_dir / "b.txt").unlink()
    progress = ctx.workspace.run_dir / "b_progress.jsonl"
    progress.write_text("{}\n")
    events.clear()

    await run_dag(ctx, resume=True, stages=stages)
    assert events == ["start:b", "end:b"]
    assert progress.exists()

    await run_dag(ctx, stages=stages)
    assert not progress.exists()
