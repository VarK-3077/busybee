"""Compile a single Lean file inside the Lake project and parse its diagnostics."""

import asyncio
import time
from pathlib import Path

from busybee.lean.errors import parse_errors
from busybee.lean.project import ensure_built, project_dir
from busybee.lean.toolchain import find_lake, toolchain_version
from busybee.schema.lean import CompileResult


async def compile_file(path: str | Path, timeout_s: float = 120) -> CompileResult:
    """Run `lake env lean <path>` and return its output, errors, and timing."""
    source_path = Path(path).resolve()
    toolchain = toolchain_version()
    lake = find_lake()
    if lake is None:
        return CompileResult(ok=False, stderr="lake not found", toolchain=toolchain)
    if not source_path.is_file():
        return CompileResult(
            ok=False,
            stderr=f"Lean file not found: {source_path}",
            toolchain=toolchain,
        )
    build = await ensure_built()
    if not build.ok:
        return build
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        lake,
        "env",
        "lean",
        str(source_path),
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
        return CompileResult(
            ok=False,
            stderr=f"Lean compilation timed out after {timeout_s:.0f}s",
            duration_s=time.monotonic() - started,
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
