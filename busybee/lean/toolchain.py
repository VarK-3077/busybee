"""Locate the elan-managed Lean toolchain used by the BusyBee Lean project."""

import functools
import shutil
import subprocess
from pathlib import Path


def _elan_binary(name: str) -> str | None:
    """Return an elan binary path when the default install location has it."""
    candidate = Path.home() / ".elan" / "bin" / name
    return str(candidate) if candidate.is_file() else None


def find_lean() -> str | None:
    """Return the lean executable from PATH or ~/.elan/bin, or None if absent."""
    return shutil.which("lean") or _elan_binary("lean")


def find_lake() -> str | None:
    """Return the lake executable from PATH or ~/.elan/bin, or None if absent."""
    return shutil.which("lake") or _elan_binary("lake")


@functools.lru_cache(maxsize=1)
def toolchain_version() -> str:
    """Return the first line of `lean --version`, or an empty string when unavailable."""
    lean = find_lean()
    if lean is None:
        return ""
    project = Path(__file__).resolve().parents[2] / "lean"
    try:
        completed = subprocess.run(
            [lean, "--version"],
            cwd=str(project) if project.is_dir() else None,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = completed.stdout.strip() or completed.stderr.strip()
    if not output or output.startswith("error:"):
        return ""
    return output.splitlines()[0]
