"""Search project history tool specification.

This provides a unified way for all models (OpenAI and Gemini) to search
across project history stores without the 2-store limitation.
"""

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.search_history import SearchHistoryService


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
    service_cls = SearchHistoryService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 30  # 30 second timeout for searches

    # Parameters
    query = Route.prompt(description="Search query or semicolon-separated queries")
    max_results = Route.prompt(
        description="Maximum results to return (default: 40)",
        default=40,
    )
    store_types = Route.prompt(
        description="Types of stores to search (default: ['conversation', 'commit'])",
        default_factory=lambda: ["conversation", "commit"],
    )