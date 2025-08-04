"""Simple deterministic file hashing for deduplication."""

import hashlib
from typing import List


def compute_content_hash(content: str) -> str:
    """Compute deterministic SHA-256 hash of string content.

    Args:
        content: String content to hash

    Returns:
        SHA-256 hash as hexadecimal string
    """
    # Normalize line endings for cross-platform consistency
    content_bytes = content.encode("utf-8")
    normalized_bytes = content_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized_bytes).hexdigest()


def compute_fileset_hash(file_contents: List[str]) -> str:
    """Compute order-independent hash of multiple file contents.

    Args:
        file_contents: List of file contents (strings)

    Returns:
        SHA-256 hash as hexadecimal string representing the entire content set
    """
    if not file_contents:
        return hashlib.sha256(b"").hexdigest()

    # Compute individual content hashes for order independence
    content_hashes = []
    for content in file_contents:
        content_hash = compute_content_hash(content)
        content_hashes.append(content_hash)

    # Sort for order independence
    content_hashes.sort()

    # Hash the sorted concatenation
    combined = "|".join(content_hashes)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
