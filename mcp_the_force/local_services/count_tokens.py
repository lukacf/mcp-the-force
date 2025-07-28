"""Local service for counting tokens in project files and directories."""

from typing import Dict, Any


class CountTokensService:
    """Local service for counting tokens in specified files or directories."""

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Count tokens for specified files or directories using the same
        filtering logic as context/attachments parameters.

        Args:
            items: List of file paths or directory paths to count tokens for
            top_n: Number of top files/directories to list (default: 10)

        Returns:
            Dictionary containing:
            - total_tokens: Total token count across all files
            - total_files: Total number of files analyzed
            - largest_files: List of top N files by token count
            - largest_directories: List of top N directories by aggregated token count
        """
        items = kwargs.get("items", [])
        top_n = kwargs.get("top_n", 10)

        # Import here to avoid circular dependency
        from ..tools.token_count import CountProjectTokens

        tool = CountProjectTokens()
        tool.items = items
        tool.top_n = top_n
        return await tool.generate()
