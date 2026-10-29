"""Rescue notebook entries that the relevance filter dropped, without re-running the pipeline.

Reads `dropped.json`, takes every record with stage `verify.relevance`, and sends those entries
through `verify_entries` again (relevance judged with the bank's score input descriptions and
the condensed notebook, then citation checks). Entries that now pass are deduplicated against
the existing facts (`dedupe_facts`; existing ids never change) and the genuinely new ones get
the next free ids F0nn after the highest existing id. `dropped.json` loses the re-judged
records and gains the fresh outcome of each entry that is still dropped, so nothing is lost
or listed twice. Because new facts change every downstream result, the stages scores, infer,
adversary, compose and render are set back to `pending` in `stages.json`, which makes
`busybee run --resume` recompute exactly those.
"""

from pathlib import Path

from busybee.extract.condensed import condense_notebook
from busybee.index import embedder_from_env
from busybee.ingest.corpus_store import load_corpus
from busybee.llm.provider import Provider
from busybee.schema.facts import DroppedEntry, NotebookEntry, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.run import RunConfig, StageState, StageStatus

from .assign_ids import assign_fact_ids
from .dedupe import dedupe_facts
from .run_verify import _load_store, policy_inputs_text
from .verify_entries import STAGE_RELEVANCE, VerifyContext, verify_entries

DOWNSTREAM_STAGES = ("scores", "infer", "adversary", "compose", "render")


def _highest_fact_number(facts: list[VerifiedFact]) -> int:
    return max((int(f.fact_id[1:]) for f in facts if f.fact_id[1:].isdigit()), default=0)


def mark_downstream_pending(stages_path: Path) -> None:
    """Set the stages after verify back to pending so a resumed run recomputes them."""
    if not stages_path.is_file():
        return
    statuses = {s.name: s for s in read_models(stages_path, StageStatus)}
    for name in DOWNSTREAM_STAGES:
        if name in statuses:
            statuses[name] = StageStatus(name=name, state=StageState.pending)
    write_models_atomic(stages_path, list(statuses.values()))


async def rescue_dropped(
    workspace_dir: str | Path,
    cfg: RunConfig,
    provider: Provider,
    banks_dir: str | Path | None = None,
) -> list[VerifiedFact]:
    """Re-judge relevance-dropped entries; append the rescued facts and return them."""
    workspace = Path(workspace_dir)
    dropped_path = workspace / "dropped.json"
    dropped = read_models(dropped_path, DroppedEntry)
    redo = [item.entry for item in dropped if item.stage == STAGE_RELEVANCE]
    if not redo:
        return []
    notebook = read_models(workspace / "notebook.json", NotebookEntry)
    store = _load_store(workspace)
    ctx = VerifyContext(
        provider=provider,
        chunks_by_id=load_corpus(workspace).chunks_by_id,
        store=store,
        embedder=embedder_from_env() if store is not None else None,
        notebook_context=condense_notebook(notebook),
        required_inputs=policy_inputs_text(banks_dir, cfg.bank_id),
    )
    rescued, still_dropped = await verify_entries(redo, ctx)

    existing = read_models(workspace / "verified_facts.json", VerifiedFact)
    merged = dedupe_facts([*existing, *rescued])
    kept, fresh = merged[: len(existing)], merged[len(existing) :]
    appended = assign_fact_ids(fresh, start=_highest_fact_number(existing) + 1)
    redone_ids = {entry.entry_id for entry in redo}
    remaining = [
        item
        for item in dropped
        if not (item.stage == STAGE_RELEVANCE and item.entry.entry_id in redone_ids)
    ]
    write_models_atomic(workspace / "verified_facts.json", [*kept, *appended])
    write_models_atomic(dropped_path, [*remaining, *still_dropped])
    if rescued:
        mark_downstream_pending(workspace / "stages.json")
    return appended
