"""Read and write `stages.json`, the resumable per-stage status record of a run.

Writes are atomic and synchronous, and the orchestrator is a single asyncio thread, so
concurrent stages never interleave a write.
"""

from datetime import UTC, datetime
from pathlib import Path

from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.run import StageState, StageStatus


def read_statuses(path: Path) -> dict[str, StageStatus]:
    """Return the recorded statuses by stage name, or {} when no file exists yet."""
    if not path.exists():
        return {}
    return {status.name: status for status in read_models(path, StageStatus)}


def write_statuses(path: Path, statuses: dict[str, StageStatus]) -> None:
    """Persist all statuses atomically."""
    write_models_atomic(path, list(statuses.values()))


def _update(path: Path, name: str, **changes: object) -> None:
    statuses = read_statuses(path)
    current = statuses.get(name, StageStatus(name=name))
    statuses[name] = current.model_copy(update=changes)
    write_statuses(path, statuses)


def mark_running(path: Path, name: str) -> None:
    """Record that a stage started."""
    _update(
        path,
        name,
        state=StageState.running,
        started_at=datetime.now(UTC),
        finished_at=None,
        error=None,
    )


def mark_done(path: Path, name: str) -> None:
    """Record that a stage finished successfully."""
    _update(path, name, state=StageState.done, finished_at=datetime.now(UTC), error=None)


def mark_failed(path: Path, name: str, error: str) -> None:
    """Record that a stage failed, with its error text."""
    _update(path, name, state=StageState.failed, finished_at=datetime.now(UTC), error=error)
