"""Shared token calculation utilities."""

from .token_counter import count_tokens


def file_wrapper_tokens(file_path: str) -> int:
    """Calculate token cost of XML wrapper tags for a file.

    Each inline file gets wrapped in <file path="...">content</file>
    This counts the tokens for just the wrapper, not the content.

    Args:
        file_path: Path to the file (used in XML path attribute)

    Returns:
        Number of tokens for the XML wrapper markup
    """
    markup = f'<file path="{file_path}"></file>'
    return count_tokens([markup])
