"""Run the whole pipeline: configure the limiter and audit log, execute the DAG, return the bundle.

`run_pipeline(cfg)` is the single entry point used by the CLI, the end-to-end tests and the
evaluator. Providers are built per stage from `BUSYBEE_LLM_*` environment variables.
"""

from pathlib import Path

from busybee.llm import audit_log, limiter
from busybee.schema.io import write_model_atomic
from busybee.schema.run import RunConfig

from .dag import run_dag
from .stages import RunContext
from .workspace import Workspace

DEFAULT_BANKS_DIR = Path(__file__).resolve().parents[2] / "banks"


async def run_pipeline(
    cfg: RunConfig, *, resume: bool = False, banks_dir: str | Path | None = None
) -> Path:
    """Run every stage (skipping finished ones when resuming) and return the bundle path."""
    workspace = Workspace(cfg.workspace_dir.parent, cfg.workspace_dir.name)
    workspace.ensure()
    limiter.configure(cfg.concurrency)
    audit_log.configure(workspace.llm_log)
    write_model_atomic(workspace.run_dir / "run.json", cfg)
    ctx = RunContext(
        cfg=cfg,
        workspace=workspace,
        banks_dir=Path(banks_dir) if banks_dir is not None else DEFAULT_BANKS_DIR,
    )
    try:
        await run_dag(ctx, resume=resume)
    finally:
        audit_log.configure(None)
        write_model_atomic(workspace.run_dir / "run.json", cfg)
    return cfg.out_dir
