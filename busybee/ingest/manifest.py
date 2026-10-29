"""Read the optional manifest.json that overrides document titles and kinds."""

from pathlib import Path

from busybee.schema.io import read_json


def load_manifest(docs_dir: str | Path) -> dict[str, dict[str, str]]:
    """Return filename -> {title, kind} overrides, or an empty mapping if absent."""
    path = Path(docs_dir) / "manifest.json"
    if not path.exists():
        return {}
    raw = read_json(path)
    if not isinstance(raw, dict):
        return {}
    manifest: dict[str, dict[str, str]] = {}
    for filename, entry in raw.items():
        if isinstance(entry, dict):
            manifest[str(filename)] = {str(key): str(value) for key, value in entry.items()}
    return manifest
