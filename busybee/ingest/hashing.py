"""Compute the SHA-256 digest of a source document."""

import hashlib
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
