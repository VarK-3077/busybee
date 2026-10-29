"""Atomic JSON and JSONL helpers for the workspace files written between stages."""

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _as_path(path: str | Path) -> Path:
    """Normalise a path argument without requiring every caller to import Path."""
    return path if isinstance(path, Path) else Path(path)


def _prepare(path: Path) -> Path:
    """Create the parent directory and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json_atomic(path: str | Path, data: Any) -> None:
    """Serialise data to JSON and replace path only after the full write succeeds."""
    target = _prepare(_as_path(path))
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def read_json(path: str | Path) -> Any:
    """Read and deserialise one JSON file."""
    return json.loads(_as_path(path).read_text(encoding="utf-8"))


def write_model_atomic(path: str | Path, model: BaseModel) -> None:
    """Write one pydantic model as JSON atomically."""
    write_json_atomic(path, model.model_dump(mode="json"))


def read_model[ModelT: BaseModel](path: str | Path, model: type[ModelT]) -> ModelT:
    """Read one pydantic model from a JSON file."""
    return model.model_validate(read_json(path))


def write_models_atomic(path: str | Path, models: Iterable[BaseModel]) -> None:
    """Write a sequence of pydantic models as one JSON array atomically."""
    write_json_atomic(path, [model.model_dump(mode="json") for model in models])


def read_models[ModelT: BaseModel](path: str | Path, model: type[ModelT]) -> list[ModelT]:
    """Read a JSON array into a list of pydantic models."""
    return [model.model_validate(item) for item in read_json(path)]


def append_jsonl(path: str | Path, model: BaseModel) -> None:
    """Append one pydantic model as a single JSON line."""
    target = _prepare(_as_path(path))
    with target.open("a", encoding="utf-8") as handle:
        handle.write(model.model_dump_json() + "\n")


def read_jsonl[ModelT: BaseModel](path: str | Path, model: type[ModelT]) -> list[ModelT]:
    """Read all non-empty JSONL lines as pydantic models, or [] if the file is absent."""
    target = _as_path(path)
    if not target.exists():
        return []
    lines = target.read_text(encoding="utf-8").splitlines()
    return [model.model_validate_json(line) for line in lines if line.strip()]
