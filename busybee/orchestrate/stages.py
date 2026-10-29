"""The stage registry: name, dependencies, async runner and expected outputs of every stage.

The DAG is exactly ARCHITECTURE section 2: ingest -> index, ingest -> extract,
extract + index -> verify, verify -> scores, verify -> infer, scores + infer -> adversary,
adversary -> compose, compose -> render. A stage's `outputs` are the files that prove it
finished, which is what lets a resumed run re-run a stage whose output has been deleted.
Stage packages are imported lazily so listing the registry stays cheap.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from busybee.llm.provider import Provider
from busybee.llm.registry import provider_from_env
from busybee.schema.run import RunConfig

from .workspace import Workspace


@dataclass(frozen=True)
class RunContext:
    """What every stage runner receives."""

    cfg: RunConfig
    workspace: Workspace
    banks_dir: Path


@dataclass(frozen=True)
class Stage:
    """One pipeline stage."""

    name: str
    dependencies: tuple[str, ...]
    run: Callable[[RunContext], Awaitable[object]]
    outputs: Callable[[RunContext], list[Path]]


def _provider(ctx: RunContext, stage: str) -> Provider:
    return provider_from_env(stage)


async def _ingest(ctx: RunContext) -> object:
    from busybee.ingest.run_ingest import run_ingest

    return await run_ingest(ctx.cfg.docs_dir, ctx.workspace.run_dir)


async def _index(ctx: RunContext) -> object:
    from busybee.index.build_index import run_index

    return await run_index(ctx.workspace.run_dir)


async def _extract(ctx: RunContext) -> object:
    from busybee.extract.run_extract import run_extract

    return await run_extract(
        ctx.workspace.run_dir, ctx.cfg, _provider(ctx, "extract"), ctx.banks_dir
    )


async def _verify(ctx: RunContext) -> object:
    from busybee.verify.run_verify import run_verify

    return await run_verify(ctx.workspace.run_dir, ctx.cfg, _provider(ctx, "verify"), ctx.banks_dir)


async def _scores(ctx: RunContext) -> object:
    from busybee.policy.run_scores import run_scores

    return await run_scores(ctx.workspace.run_dir, ctx.cfg, _provider(ctx, "scores"), ctx.banks_dir)


async def _infer(ctx: RunContext) -> object:
    from busybee.infer.run_infer import run_infer

    return await run_infer(ctx.workspace.run_dir, ctx.cfg, _provider(ctx, "infer"))


async def _adversary(ctx: RunContext) -> object:
    from busybee.adversary.run_adversary import run_adversary

    return await run_adversary(ctx.workspace.run_dir, ctx.cfg, _provider(ctx, "adversary"))


async def _compose(ctx: RunContext) -> object:
    from busybee.compose.run_compose import run_compose

    return await run_compose(
        ctx.workspace.run_dir, ctx.cfg, _provider(ctx, "compose"), ctx.banks_dir
    )


async def _render(ctx: RunContext) -> object:
    import asyncio

    from busybee.render.bundle import render_bundle

    return await asyncio.to_thread(
        render_bundle,
        ctx.workspace.run_dir,
        ctx.cfg.out_dir,
        ctx.banks_dir,
        ctx.cfg.report_min_importance,
        ctx.cfg.report_max_facts_per_category,
    )


STAGES: tuple[Stage, ...] = (
    Stage("ingest", (), _ingest, lambda c: [c.workspace.documents]),
    Stage("index", ("ingest",), _index, lambda c: [c.workspace.vectors]),
    Stage("extract", ("ingest",), _extract, lambda c: [c.workspace.notebook]),
    Stage("verify", ("extract", "index"), _verify, lambda c: [c.workspace.verified_facts]),
    Stage("scores", ("verify",), _scores, lambda c: [c.workspace.scores]),
    Stage("infer", ("verify",), _infer, lambda c: [c.workspace.inferences]),
    Stage("adversary", ("scores", "infer"), _adversary, lambda c: [c.workspace.concerns]),
    Stage("compose", ("adversary",), _compose, lambda c: [c.workspace.report]),
    Stage("render", ("compose",), _render, lambda c: [c.cfg.out_dir / "index.html"]),
)


def stage_names() -> list[str]:
    """Return the stage names in a valid execution order."""
    return [stage.name for stage in STAGES]
