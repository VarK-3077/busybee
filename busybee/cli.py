"""The typer command line: run the pipeline, evaluate a company, or formalise a bank."""

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="BusyBee credit-review pipeline.")

DEFAULT_BANKS_DIR = Path("banks")


@app.command()
def run(
    docs: Annotated[Path, typer.Option("--docs", help="Directory of source documents.")],
    bank: Annotated[str, typer.Option("--bank", help="Bank id under banks/.")],
    out: Annotated[Path, typer.Option("--out", help="Output directory for the HTML bundle.")],
    run_id: Annotated[str | None, typer.Option("--run-id", help="Explicit run id.")] = None,
    resume: Annotated[bool, typer.Option("--resume", help="Resume an existing run.")] = False,
    workspace: Annotated[
        Path, typer.Option("--workspace", help="Directory holding per-run workspaces.")
    ] = Path("workspace"),
    banks_dir: Annotated[
        Path, typer.Option("--banks-dir", help="Directory holding bank folders.")
    ] = DEFAULT_BANKS_DIR,
    proposed_exposure: Annotated[
        str | None,
        typer.Option(
            "--proposed-exposure",
            help="Proposed aggregate bank exposure, INR crore (env BUSYBEE_PROPOSED_EXPOSURE).",
        ),
    ] = None,
    projected_turnover: Annotated[
        str | None,
        typer.Option(
            "--projected-turnover",
            help="Projected next-year turnover, INR crore (env BUSYBEE_PROJECTED_TURNOVER).",
        ),
    ] = None,
) -> None:
    """Run the full pipeline on a document pack."""
    from busybee.orchestrate.config import build_run_config
    from busybee.orchestrate.dag import PipelineError
    from busybee.orchestrate.run import run_pipeline

    try:
        cfg = build_run_config(
            docs,
            bank,
            out,
            run_id=run_id,
            workspace_root=workspace,
            proposed_exposure=proposed_exposure,
            projected_turnover=projected_turnover,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    try:
        bundle = asyncio.run(run_pipeline(cfg, resume=resume, banks_dir=banks_dir.resolve()))
    except PipelineError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"report: {bundle / 'index.html'}")


CHROMIUM_BINARIES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


def find_chromium() -> str | None:
    """Return the first Chromium-family binary on PATH, or None."""
    return next((path for name in CHROMIUM_BINARIES if (path := shutil.which(name))), None)


@app.command("export-pdf")
def export_pdf(
    bundle: Annotated[Path, typer.Option("--bundle", help="Rendered bundle directory.")],
    out: Annotated[Path, typer.Option("--out", help="PDF file to write.")],
) -> None:
    """Print a rendered report bundle to a PDF with headless Chromium."""
    index = bundle.resolve() / "index.html"
    if not index.is_file():
        typer.echo(f"no index.html in {bundle}", err=True)
        raise typer.Exit(code=1)
    chromium = find_chromium()
    if chromium is None:
        typer.echo(
            "export-pdf needs Chromium; install one of: " + ", ".join(CHROMIUM_BINARIES),
            err=True,
        )
        raise typer.Exit(code=1)
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        chromium,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={out}",
        "--no-pdf-header-footer",
        index.as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0 or not out.is_file():
        typer.echo(f"chromium failed: {result.stderr.strip()[-400:]}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"pdf: {out}")


@app.command()
def rescue(
    workspace: Annotated[Path, typer.Option("--workspace", help="Run directory to rescue in.")],
    bank: Annotated[str, typer.Option("--bank", help="Bank id under banks/.")],
    banks_dir: Annotated[
        Path, typer.Option("--banks-dir", help="Directory holding bank folders.")
    ] = DEFAULT_BANKS_DIR,
) -> None:
    """Re-judge relevance-dropped entries and queue downstream stages for `run --resume`."""
    from busybee.llm.registry import provider_from_env
    from busybee.schema.run import RunConfig
    from busybee.verify.rescue import rescue_dropped

    run_json = workspace / "run.json"
    if not run_json.is_file():
        typer.echo(f"no run.json in {workspace}", err=True)
        raise typer.Exit(code=1)
    cfg = RunConfig.model_validate_json(run_json.read_text(encoding="utf-8")).model_copy(
        update={"bank_id": bank}
    )
    rescued = asyncio.run(
        rescue_dropped(workspace, cfg, provider_from_env("verify"), banks_dir.resolve())
    )
    typer.echo(f"rescued {len(rescued)} fact(s): {', '.join(f.fact_id for f in rescued) or '-'}")


@app.command()
def eval(
    workspace_dir: Annotated[
        Path, typer.Option("--workspace-dir", help="Workspace directory of a completed run.")
    ],
    company: Annotated[
        str | None, typer.Option("--company", help="Company name used to find the gold set.")
    ] = None,
    bank: Annotated[str | None, typer.Option("--bank", help="Bank id under banks/.")] = None,
    gold: Annotated[Path | None, typer.Option("--gold", help="Explicit gold JSON path.")] = None,
    eval_root: Annotated[
        Path, typer.Option("--eval-root", help="Directory receiving eval/<run_id>/ outputs.")
    ] = Path("eval"),
    repeats: Annotated[
        int,
        typer.Option(
            "--repeats", min=1, help="Run the LLM-judged metrics N times; report mean/min/max."
        ),
    ] = 1,
) -> None:
    """Evaluate a completed run against gold facts and print the metrics table."""
    from busybee.eval.run_eval import cli_eval

    out_dir, markdown = cli_eval(
        workspace_dir,
        company=company,
        bank_id=bank,
        gold_path=gold,
        eval_root=eval_root,
        repeats=repeats,
    )
    typer.echo(markdown)
    typer.echo(f"wrote {out_dir}")


@app.command()
def ask(
    question: Annotated[
        str | None, typer.Argument(help="Question to answer from the run's documents.")
    ] = None,
    workspace_dir: Annotated[
        Path, typer.Option("--workspace-dir", help="Workspace directory of a completed run.")
    ] = Path("workspace"),
    interactive: Annotated[
        bool, typer.Option("--interactive", help="Keep asking questions until a blank line.")
    ] = False,
) -> None:
    """Answer a question from the run's documents, marking each sentence supported or not."""
    from busybee.ask.render_answer import render_answer
    from busybee.ask.run_ask import answer_question, chat_loop
    from busybee.llm.registry import provider_from_env

    if question is None and not interactive:
        typer.echo("give a question or --interactive", err=True)
        raise typer.Exit(code=2)
    provider = provider_from_env("ask")
    try:
        if question is not None:
            answer = asyncio.run(answer_question(workspace_dir, question, provider))
            typer.echo(render_answer(answer))
        if interactive:
            asyncio.run(chat_loop(workspace_dir, provider, lambda: input("ask> "), typer.echo))
    except FileNotFoundError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error


@app.command()
def formalize(
    bank: Annotated[str, typer.Option("--bank", help="Bank id under banks/.")],
    banks_dir: Annotated[
        Path, typer.Option("--banks-dir", help="Directory holding bank folders.")
    ] = DEFAULT_BANKS_DIR,
    workspace: Annotated[
        Path, typer.Option("--workspace", help="Scratch directory for formalisation rounds.")
    ] = Path("workspace/formalize"),
) -> None:
    """Formalise a bank policy into Lean."""
    from busybee.llm.registry import provider_from_env
    from busybee.policy.bank_fs import bank_dir, load_bank, save_formalisation
    from busybee.policy.formalize.loop import formalise

    async def formalise_bank() -> Path:
        provider = provider_from_env("formalize")
        policy = load_bank(banks_dir, bank)
        result = await formalise(provider, policy, workspace / bank)
        return save_formalisation(bank_dir(banks_dir, bank), result.source, provider.model)

    path = asyncio.run(formalise_bank())
    typer.echo(f"wrote {path} (unapproved; needs human review)")


if __name__ == "__main__":
    app()
