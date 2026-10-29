"""Run the stage DAG with asyncio: ready stages start concurrently, failures block dependants.

A stage is ready when all its dependencies are done. When a stage fails, its dependants never
start but independent stages still finish. On resume a stage is skipped only if it is recorded
`done`, its output files still exist, and every dependency was skipped too; a stage that has
to re-run therefore re-runs everything downstream of it. A stage left `running` (the process
died) or `failed` is therefore re-run, and the long stages (extract, verify) pick up their
`*_progress.jsonl` checkpoint files so the re-run continues instead of restarting. Without
`resume` those checkpoint files are deleted so a fresh run never reuses old progress.
"""

import asyncio
from collections.abc import Sequence

from busybee.schema.run import StageState

from .stages import STAGES, RunContext, Stage
from .status import mark_done, mark_failed, mark_running, read_statuses


class PipelineError(RuntimeError):
    """Raised after the DAG settles when at least one stage failed."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        detail = "; ".join(f"{name}: {error}" for name, error in errors.items())
        super().__init__(f"pipeline failed: {detail}")


def skippable_stages(stages: Sequence[Stage], ctx: RunContext) -> set[str]:
    """Return the stages a resumed run may skip."""
    statuses = read_statuses(ctx.workspace.stages)
    skip: set[str] = set()
    for stage in stages:
        status = statuses.get(stage.name)
        finished = status is not None and status.state is StageState.done
        outputs_exist = all(path.exists() for path in stage.outputs(ctx))
        if finished and outputs_exist and all(dep in skip for dep in stage.dependencies):
            skip.add(stage.name)
    return skip


async def _run_stage(stage: Stage, ctx: RunContext) -> None:
    path = ctx.workspace.stages
    mark_running(path, stage.name)
    try:
        await stage.run(ctx)
    except Exception as error:
        mark_failed(path, stage.name, f"{type(error).__name__}: {error}")
        raise
    mark_done(path, stage.name)


async def run_dag(
    ctx: RunContext, *, resume: bool = False, stages: Sequence[Stage] = STAGES
) -> None:
    """Execute the stages; raise PipelineError once everything runnable has finished."""
    done = skippable_stages(stages, ctx) if resume else set()
    if not resume:
        ctx.workspace.stages.unlink(missing_ok=True)
        for progress in ctx.workspace.run_dir.glob("*_progress.jsonl"):
            progress.unlink(missing_ok=True)
    started = set(done)
    running: dict[asyncio.Task[None], str] = {}
    errors: dict[str, str] = {}
    while True:
        for stage in stages:
            if stage.name in started:
                continue
            if all(dep in done for dep in stage.dependencies):
                started.add(stage.name)
                running[asyncio.create_task(_run_stage(stage, ctx))] = stage.name
        if not running:
            break
        finished, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
        for task in finished:
            name = running.pop(task)
            error = task.exception()
            if error is None:
                done.add(name)
            else:
                errors[name] = f"{type(error).__name__}: {error}"
    if errors:
        raise PipelineError(errors)
