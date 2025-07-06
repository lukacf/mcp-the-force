"""
Token counting tool for project files.
"""

import asyncio
import os
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional, DefaultDict, cast

from ..utils.context_loader import load_text_files


class CountProjectTokens:
    """
    Count tokens for specified files or directories using the same
    filtering logic as context/attachments parameters.
    """

    def __init__(self):
        self.items: List[str] = []
        self.top_n: Optional[int] = 10

    async def generate(self) -> Dict[str, Any]:
        """
        Count tokens for all text files in the specified items.

        Returns:
            Dictionary containing:
            - total_tokens: Total token count across all files
            - total_files: Total number of files analyzed
            - largest_files: List of top N files by token count
            - largest_directories: List of top N directories by aggregated token count
        """
        # Validate that items are provided
        if not self.items:
            raise ValueError("At least one file or directory path must be provided")

        # Load files and get their content + token counts
        # Use asyncio.to_thread to prevent blocking the event loop during file I/O
        file_data = await asyncio.to_thread(load_text_files, self.items)

        if not file_data:
            return {
                "total_tokens": 0,
                "total_files": 0,
                "largest_files": [],
                "largest_directories": [],
            }

        # Initialize data structures
        all_files = []
        dir_aggregates: DefaultDict[str, Dict[str, int]] = defaultdict(
            lambda: {"tokens": 0, "file_count": 0}
        )
        total_tokens = 0

        # Determine the common base path for relative path calculation
        try:
            common_base_path = Path(os.path.commonpath([item[0] for item in file_data]))
        except ValueError:
            # If no common path, use the current directory
            common_base_path = Path.cwd()

        # Process each file for individual and directory stats
        for file_path_str, content, token_count in file_data:
            total_tokens += token_count
            file_path = Path(file_path_str)
            all_files.append({"path": file_path_str, "tokens": token_count})

            # Aggregate counts for all parent directories
            # Include the file's immediate parent and all ancestors
            current_path = file_path.parent
            while current_path != current_path.parent:  # Stop at root
                dir_aggregates[str(current_path)]["tokens"] += token_count
                dir_aggregates[str(current_path)]["file_count"] += 1
                # If we've reached the common base path, we can stop
                try:
                    if current_path.samefile(common_base_path):
                        break
                except (OSError, ValueError):
                    pass
                current_path = current_path.parent

        # Get top N files
        top_n = self.top_n or 10  # Use default if not set
        largest_files = sorted(
            all_files, key=lambda x: cast(int, x["tokens"]), reverse=True
        )[:top_n]

        # Get top N directories
        # Convert defaultdict to a list of dicts for sorting
        dir_list = [
            {"path": path, "tokens": data["tokens"], "file_count": data["file_count"]}
            for path, data in dir_aggregates.items()
        ]
        largest_directories = sorted(
            dir_list,
            key=lambda x: cast(int, x["tokens"]),
            reverse=True,
        )[:top_n]

        return {
            "total_tokens": total_tokens,
            "total_files": len(all_files),
            "largest_files": largest_files,
            "largest_directories": largest_directories,
        }
