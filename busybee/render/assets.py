"""Copy the design language's stylesheets and scripts into a rendered bundle."""

import shutil
from pathlib import Path


def design_directory() -> Path:
    """Return the repository's design/ directory."""
    return Path(__file__).resolve().parents[2] / "design"


def copy_assets(destination: str | Path, source_dir: str | Path | None = None) -> list[Path]:
    """Copy every design/*.css and design/*.js file into destination/assets."""
    source = Path(source_dir) if source_dir is not None else design_directory()
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for pattern in ("*.css", "*.js"):
        for path in sorted(source.glob(pattern)):
            copy = target / path.name
            shutil.copy2(path, copy)
            copied.append(copy)
    return copied
