from typing import Sequence, Optional
import logging

logger = logging.getLogger(__name__)

try:
    import tiktoken

    _enc: Optional[tiktoken.Encoding] = tiktoken.get_encoding("o200k_base")
except Exception:
    _enc = None

# Max characters to pass to tiktoken encoder (prevents hangs on pathological content)
# Increased from 250k to 5M to enable accurate token counting for large codebases
# The looks_pathological() check prevents hangs on repetitive content
TOKEN_ENCODE_CHAR_CAP = 5_000_000


def looks_pathological(text: str, threshold: float = 0.15) -> bool:
    """
    Detect low-entropy content that may cause tiktoken to hang.

    Args:
        text: Text to analyze
        threshold: Ratio of distinct chars to total length below which content is considered pathological

    Returns:
        True if content appears to be highly repetitive
    """
    if len(text) < 10000:  # Too small to matter
        return False
    return len(set(text)) / len(text) < threshold


def safe_estimate_tokens(text: str) -> int:
    """Estimate token count without using tiktoken (fast fallback)."""
    return max(1, len(text) // 4)


def count_tokens(texts: Sequence[str]) -> int:
    """Count tokens in texts, with fallback for when tiktoken is unavailable or content is problematic."""
    if _enc is None:
        # Fallback: estimate ~4 chars per token
        return sum(max(1, len(t) // 4) for t in texts)

    total_tokens = 0
    for text in texts:
        # Use estimation for very large texts or pathological (repetitive) content
        if len(text) > TOKEN_ENCODE_CHAR_CAP or looks_pathological(text):
            if len(text) > TOKEN_ENCODE_CHAR_CAP:
                logger.debug(f"Using estimation for large content: {len(text)} chars")
            else:
                logger.debug(
                    f"Using estimation for pathological content: {len(text)} chars"
                )
            total_tokens += safe_estimate_tokens(text)
        else:
            try:
                total_tokens += len(_enc.encode(text))
            except Exception as e:
                logger.warning(
                    f"tiktoken encoding failed: {e}, falling back to estimation"
                )
                total_tokens += safe_estimate_tokens(text)

    return total_tokens
