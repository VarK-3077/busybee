"""Build the `RunConfig` for a run from CLI arguments, environment variables and defaults.

Defaults: window 12000 tokens, notebook budget 16000 tokens, concurrency 12 (the vLLM server
serves 16 sequences, so 12 leaves headroom for retries), extract concurrency 12 (the same
12 windows in flight; the four spare sequences absorb retries and the verify calls of a resumed
run), segmented extraction with at least 2 windows per segment (a segment of 2 windows is
24k tokens, enough rolling context for periods and supersedes, and a document of 4 or more
windows now splits into 2 or more parallel segments instead of waiting for 6).
`BUSYBEE_WINDOW_TOKENS`, `BUSYBEE_NOTEBOOK_BUDGET_TOKENS`, `BUSYBEE_CONCURRENCY`,
`BUSYBEE_EXTRACT_CONCURRENCY` (windows in flight during extract, default 12),
`BUSYBEE_SEGMENT_MIN_WINDOWS`, `BUSYBEE_EXTRACT_MODE`, `BUSYBEE_REPORT_MIN_IMPORTANCE`
(facts below it go to the report appendix, default 4) and `BUSYBEE_REPORT_MAX_PER_CATEGORY`
(main-section cap per category, default 10) override them. The bank inputs
`proposed_exposure` and `projected_turnover` (INR crore) come from the arguments, else from
`BUSYBEE_PROPOSED_EXPOSURE` / `BUSYBEE_PROJECTED_TURNOVER`, else are absent. Paths are made
absolute so stages behave the same from any working directory.
"""

import os
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path

from busybee.schema.run import ExtractMode, RunConfig

DEFAULT_WORKSPACE_ROOT = Path("workspace")
DEFAULT_WINDOW_TOKENS = 12000
DEFAULT_NOTEBOOK_BUDGET_TOKENS = 16000
DEFAULT_CONCURRENCY = 12
DEFAULT_EXTRACT_CONCURRENCY = 12
DEFAULT_SEGMENT_MIN_WINDOWS = 2
DEFAULT_REPORT_MIN_IMPORTANCE = 4
DEFAULT_REPORT_MAX_PER_CATEGORY = 10


def default_run_id(docs_dir: Path) -> str:
    """A stable run id derived from the document directory name, so --resume finds it."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", docs_dir.resolve().name).strip("-")
    return slug or "run"


def _int_from(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    return int(raw) if raw else default


def _crore_from(raw: object, name: str) -> Decimal | None:
    """Parse a positive INR crore amount; empty means not given."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        amount = Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a number of INR crore, got {raw!r}") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{name} must be a positive number of INR crore, got {raw!r}")
    return amount


def build_run_config(
    docs_dir: str | Path,
    bank_id: str,
    out_dir: str | Path,
    *,
    run_id: str | None = None,
    workspace_root: str | Path | None = None,
    proposed_exposure: str | Decimal | None = None,
    projected_turnover: str | Decimal | None = None,
    env: Mapping[str, str] | None = None,
) -> RunConfig:
    """Return the run configuration, with workspace_dir = <workspace_root>/<run_id>."""
    environment = os.environ if env is None else env
    docs = Path(docs_dir).resolve()
    resolved_id = run_id or default_run_id(docs)
    root = Path(workspace_root) if workspace_root is not None else DEFAULT_WORKSPACE_ROOT
    return RunConfig(
        run_id=resolved_id,
        docs_dir=docs,
        bank_id=bank_id,
        out_dir=Path(out_dir).resolve(),
        workspace_dir=(root / resolved_id).resolve(),
        window_tokens=_int_from(environment, "BUSYBEE_WINDOW_TOKENS", DEFAULT_WINDOW_TOKENS),
        notebook_budget_tokens=_int_from(
            environment, "BUSYBEE_NOTEBOOK_BUDGET_TOKENS", DEFAULT_NOTEBOOK_BUDGET_TOKENS
        ),
        concurrency=_int_from(environment, "BUSYBEE_CONCURRENCY", DEFAULT_CONCURRENCY),
        extract_concurrency=_int_from(
            environment, "BUSYBEE_EXTRACT_CONCURRENCY", DEFAULT_EXTRACT_CONCURRENCY
        ),
        segment_min_windows=_int_from(
            environment, "BUSYBEE_SEGMENT_MIN_WINDOWS", DEFAULT_SEGMENT_MIN_WINDOWS
        ),
        report_min_importance=_int_from(
            environment, "BUSYBEE_REPORT_MIN_IMPORTANCE", DEFAULT_REPORT_MIN_IMPORTANCE
        ),
        report_max_facts_per_category=_int_from(
            environment, "BUSYBEE_REPORT_MAX_PER_CATEGORY", DEFAULT_REPORT_MAX_PER_CATEGORY
        ),
        proposed_exposure=_crore_from(
            proposed_exposure or environment.get("BUSYBEE_PROPOSED_EXPOSURE"), "proposed exposure"
        ),
        projected_turnover=_crore_from(
            projected_turnover or environment.get("BUSYBEE_PROJECTED_TURNOVER"),
            "projected turnover",
        ),
        extract_mode=ExtractMode(environment.get("BUSYBEE_EXTRACT_MODE") or "segmented"),
    )
