"""Manage the Lake project: locate it, build it once, and sync generated policy modules."""

import asyncio
import hashlib
import os
import re
import time
from pathlib import Path

from busybee.lean.errors import parse_errors
from busybee.lean.toolchain import find_lake, toolchain_version
from busybee.schema.lean import CompileResult

_BUILD_LOCK = asyncio.Lock()


def project_dir() -> Path:
    """Return the repository's lean/ directory."""
    return Path(__file__).resolve().parents[2] / "lean"


def runs_dir(run_id: str) -> Path:
    """Create and return lean/Runs/<run_id> for generated per-run Lean files."""
    target = project_dir() / "Runs" / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def camel_bank_id(bank_id: str) -> str:
    """Turn a bank id such as `demo_bank` into a Lean module name `DemoBank`."""
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", bank_id) if part]
    name = "".join(part[:1].upper() + part[1:] for part in parts)
    if not name:
        raise ValueError(f"invalid bank id: {bank_id!r}")
    return f"Bank{name}" if name[0].isdigit() else name


def _library_sources() -> list[Path]:
    """Return the lakefile, toolchain pin, and every library Lean source."""
    root = project_dir()
    files = [root / "lakefile.toml", root / "lean-toolchain", root / "BusyBee.lean"]
    files.extend(sorted((root / "BusyBee").rglob("*.lean")))
    return [path for path in files if path.is_file()]


def _source_digest() -> str:
    """Hash the relative path and content of every library source."""
    digest = hashlib.sha256()
    root = project_dir()
    for path in _library_sources():
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _marker_path() -> Path:
    """Return the build-cache marker path inside the Lake build directory."""
    return project_dir() / ".lake" / "busybee-build.hash"


def _write_atomic(path: Path, text: str) -> None:
    """Replace path with text only after the temporary write succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


async def _run_lake_build(timeout_s: float) -> CompileResult:
    """Run `lake build` in the project directory and capture its output."""
    lake = find_lake()
    toolchain = toolchain_version()
    if lake is None:
        return CompileResult(ok=False, stderr="lake not found", toolchain=toolchain)
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        lake,
        "build",
        cwd=str(project_dir()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_s
        )
    except TimeoutError:
        process.kill()
        await process.communicate()
        duration = time.monotonic() - started
        return CompileResult(
            ok=False,
            stderr=f"lake build timed out after {timeout_s:.0f}s",
            duration_s=duration,
            toolchain=toolchain,
        )
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    errors = parse_errors(stderr)
    for error in parse_errors(stdout):
        if error not in errors:
            errors.append(error)
    return CompileResult(
        ok=process.returncode == 0 and not errors,
        stdout=stdout,
        stderr=stderr,
        duration_s=time.monotonic() - started,
        toolchain=toolchain,
        errors=errors,
    )


async def ensure_built(timeout_s: float = 600) -> CompileResult:
    """Build the Lake project unless the marker matches the current library sources."""
    async with _BUILD_LOCK:
        digest = _source_digest()
        marker = _marker_path()
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == digest:
            return CompileResult(
                ok=True,
                stdout="lake build: up to date",
                toolchain=toolchain_version(),
            )
        result = await _run_lake_build(timeout_s)
        if result.ok:
            _write_atomic(marker, digest + "\n")
        return result


def _policy_path(bank_id: str) -> tuple[str, Path]:
    """Return the module name and destination path for one bank policy."""
    module = camel_bank_id(bank_id)
    return f"BusyBee.Policy.{module}", project_dir() / "BusyBee" / "Policy" / f"{module}.lean"


async def sync_policy_module(bank_id: str, source: str) -> str:
    """Atomically write a bank policy module and rebuild when its source changed."""
    module_name, target = _policy_path(bank_id)
    text = source if source.endswith("\n") else source + "\n"
    if target.is_file() and target.read_text(encoding="utf-8") == text:
        return module_name
    _write_atomic(target, text)
    result = await ensure_built()
    if not result.ok:
        raise RuntimeError(f"lake build failed after syncing {module_name}:\n{result.stderr}")
    return module_name
