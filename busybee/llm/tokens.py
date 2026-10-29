"""Token counting and truncation with tiktoken, falling back to a character estimate."""

_ENCODING_NAME = "cl100k_base"
_encoding: object | None = None
_encoding_failed = False


def _get_encoding() -> object | None:
    global _encoding, _encoding_failed
    if _encoding_failed:
        return None
    if _encoding is not None:
        return _encoding
    try:
        import tiktoken
    except ImportError:
        _encoding_failed = True
        return None
    try:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    except Exception:
        _encoding_failed = True
        return None
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens with cl100k_base, or approximate with one token per four characters."""
    if not text:
        return 0
    encoding = _get_encoding()
    if encoding is None:
        return max(1, len(text) // 4)
    return len(encoding.encode(text))


def truncate_to_tokens(text: str, n: int) -> str:
    """Return a prefix of text no longer than n tokens."""
    if n <= 0:
        return ""
    encoding = _get_encoding()
    if encoding is None:
        return text[: n * 4]
    tokens = encoding.encode(text)
    if len(tokens) <= n:
        return text
    return encoding.decode(tokens[:n])
