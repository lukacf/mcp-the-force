from typing import Sequence, Optional

try:
    import tiktoken

    _enc: Optional[tiktoken.Encoding] = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None


def count_tokens(texts: Sequence[str]) -> int:
    """Count tokens in texts, with fallback for when tiktoken is unavailable."""
    if _enc is None:
        # Fallback: estimate ~4 chars per token
        return sum(max(1, len(t) // 4) for t in texts)
    return sum(len(_enc.encode(t)) for t in texts)
