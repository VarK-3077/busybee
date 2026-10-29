"""SHA-256 hashing for Lean sources so artifacts and build caches stay reproducible."""

import hashlib


def sha256_text(source: str) -> str:
    """Return the hexadecimal SHA-256 digest of source text encoded as UTF-8."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def sha256(source: str) -> str:
    """Alias for sha256_text, the digest used by LeanArtifact.sha256."""
    return sha256_text(source)
