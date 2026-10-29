"""Run configuration and per-stage status records used for orchestration."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class ExtractMode(StrEnum):
    """How rolling notebooks are split: per document segment, per document, or over the corpus."""

    segmented = "segmented"
    per_document = "per_document"
    global_ = "global"


class StageState(StrEnum):
    """The lifecycle state of one pipeline stage."""

    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class RunConfig(BaseModel):
    """Everything a run needs to locate inputs, outputs, and models."""

    run_id: str
    docs_dir: Path
    bank_id: str
    out_dir: Path
    workspace_dir: Path
    window_tokens: int = 12000
    notebook_budget_tokens: int = 16000
    concurrency: int = 12
    extract_concurrency: int = 12
    extract_mode: ExtractMode = ExtractMode.segmented
    segment_min_windows: int = 2
    report_min_importance: int = 4
    report_max_facts_per_category: int = 10
    models: dict[str, str] = Field(default_factory=dict)
    proposed_exposure: Decimal | None = None
    projected_turnover: Decimal | None = None


class StageStatus(BaseModel):
    """The resumable status record for one stage in stages.json."""

    name: str
    state: StageState = StageState.pending
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
