"""Count project tokens tool."""

from typing import List, Optional
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.count_tokens import CountTokensService


@tool
class CountProjectTokens(ToolSpec):
    """
    Count tokens for specified files or directories using the same
    filtering logic as context/attachments parameters.
    """

    model_name = "count_project_tokens"
    description = (
        "Count tokens for specified files or directories. This tool recursively "
        "scans paths, counts tokens in text files (respecting .gitignore), and "
        "returns an aggregated report. It uses the same file filtering logic "
        "as context parameters, skipping binaries and respecting size limits."
    )

    # This is a local service, not an AI model
    service_cls = CountTokensService  # Use actual class, not string
    adapter_class = None
    timeout = 60

    items: List[str] = Route.adapter(  # type: ignore[assignment]
        description=(
            "(Required) A list of file and/or directory paths to analyze. The tool will "
            "recursively scan the provided paths, count the tokens in all text files "
            "(respecting .gitignore), and return an aggregated report. Uses the same file "
            "filtering logic as the context parameter - skips binaries, respects size limits "
            "(500KB/file, 50MB total), and supports 60+ text file types. "
            "Syntax: An array of strings (not a JSON string). Do not wrap the array in quotes. "
            "Each string must be an absolute path. "
            'Example: ["/path/to/project/main.py", "/path/to/project/utils/"]'
        )
    )

    top_n: Optional[int] = Route.adapter(  # type: ignore[assignment]
        default=10,
        description=(
            "(Optional) The number of top files and directories to include in the "
            "'largest_files' and 'largest_directories' sections of the report. Helps identify "
            "which files/directories consume the most tokens in your context window. "
            "Syntax: An integer. "
            "Default: 10. "
            "Example: top_n=20"
        ),
    )
