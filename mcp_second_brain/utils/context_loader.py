"""
Shared context loading functionality for file gathering and token counting.
"""

from pathlib import Path
from typing import List, Tuple

from .fs import gather_file_paths
from .token_counter import count_tokens


def load_text_files(items: List[str]) -> List[Tuple[str, str, int]]:
    """
    Load text files and return their paths, contents, and token counts.

    This function uses the same file gathering and filtering logic as the
    prompt builder, ensuring consistency across the application.

    Args:
        items: List of file paths or directory paths to process

    Returns:
        List of tuples containing (file_path, content, token_count)
        Binary files, oversized files, and gitignored files are automatically
        filtered out by gather_file_paths.
    """
    paths = gather_file_paths(items)
    result: List[Tuple[str, str, int]] = []

    for path in paths:
        try:
            # Read file content with UTF-8 encoding, ignoring errors
            content = Path(path).read_text(encoding="utf-8", errors="ignore")

            # Remove null bytes which can cause issues
            content = content.replace("\x00", "")

            # Count tokens for this content
            token_count = count_tokens([content])

            result.append((path, content, token_count))

        except Exception:
            # Skip files that can't be read (permissions, etc.)
            # This matches the behavior of the prompt builder
            continue

    return result
