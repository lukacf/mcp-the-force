"""Simple deterministic file hashing for deduplication."""

import hashlib
from typing import List, Tuple


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


def compute_fileset_hash(files: List[Tuple[str, str]]) -> str:
    """Compute order-independent hash of multiple files, considering both path and content.

    Args:
        files: List of (file_path, file_content) tuples. Paths should be
               relative to a common project root for cross-platform consistency.

    Returns:
        SHA-256 hash as hexadecimal string representing the entire fileset
    """
    if not files:
        return hashlib.sha256(b"").hexdigest()

    # Create component hashes from (path, content) tuples for order independence
    # This ensures that both file path and content contribute to the hash
    component_hashes = []
    for path, content in files:
        content_hash = compute_content_hash(content)
        # Combine path and content hash, then hash the result for a stable component hash
        component_string = f"{path}:{content_hash}"
        component_hash = hashlib.sha256(component_string.encode("utf-8")).hexdigest()
        component_hashes.append(component_hash)

    # Sort for order independence
    component_hashes.sort()

    # Hash the sorted concatenation
    combined = "|".join(component_hashes)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
