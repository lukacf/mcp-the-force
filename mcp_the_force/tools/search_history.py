"""Search project history tool specification.

This provides a unified way for all models (OpenAI and Gemini) to search
across project history stores without the 2-store limitation.
"""

from typing import List

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.search_history import HistorySearchService


@tool
class SearchProjectHistory(ToolSpec):
    """Search across all project history stores."""

    # Required for @tool decorator
    model_name = "search_project_history"
    description = (
        "Search project history (semantic vector database search) for past decisions, conversations, and commits. "
        "⚠️ IMPORTANT: Returns HISTORICAL data that may be OUTDATED. "
        "Do NOT use to understand current code state. "
        "Best for finding past design decisions and understanding project evolution."
    )

    # Use local service instead of adapter
    service_cls = HistorySearchService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 30  # 30 second timeout for searches

    # Parameters
    query: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The query to search for in the project's history. Performs semantic "
            "search across all indexed conversations and git commits. For multiple queries, separate "
            "them with a semicolon (;). The search uses vector similarity to find relevant historical "
            "context, not exact string matching. "
            "Syntax: A string or semicolon-separated strings. "
            "Example: 'jwt authentication;refresh token logic'"
        )
    )
    max_results: int = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Optional) The maximum number of search results to return. Limits the size of the output "
            "to prevent overwhelming responses. Higher values may include less relevant results. "
            "Syntax: An integer. "
            "Default: 40. "
            "Example: max_results=20"
        ),
        default=40,
    )
    store_types: List[str] = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Optional) A list of history store types to search. Allows scoping the search to specific "
            "types of historical data. Valid options are 'conversation' (summarized AI assistant interactions), "
            "'commit' (git commit messages and changes), and 'session' (raw conversation transcripts). You can search one or multiple types. "
            "Syntax: An array of strings (not a JSON string). Do not wrap the array in quotes. "
            "Default: ['conversation', 'commit']. "
            'Example: store_types=["conversation"]'
        ),
        default_factory=lambda: ["conversation", "commit"],
    )
