"""
Token counting tool for project files.
"""

import asyncio
from typing import List, Dict, Any

from ..utils.context_loader import load_text_files


class CountProjectTokens:
    """
    Count tokens for specified files or directories using the same
    filtering logic as context/attachments parameters.
    """

    def __init__(self):
        self.items: List[str] = []

    async def generate(self) -> Dict[str, Any]:
        """
        Count tokens for all text files in the specified items.

        Returns:
            Dictionary containing:
            - total_tokens: Total token count across all files
            - per_file: Dictionary mapping file paths to their token counts
        """
        # Validate that items are provided
        if not self.items:
            raise ValueError("At least one file or directory path must be provided")

        # Load files and get their content + token counts
        # Use asyncio.to_thread to prevent blocking the event loop during file I/O
        file_data = await asyncio.to_thread(load_text_files, self.items)

        # Build the result
        per_file = {}
        total_tokens = 0

        for file_path, content, token_count in file_data:
            per_file[file_path] = token_count
            total_tokens += token_count

        return {"total_tokens": total_tokens, "per_file": per_file}
