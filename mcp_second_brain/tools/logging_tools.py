"""MCP tools for searching debug logs."""

from typing import Optional

from .base import ToolSpec
from .registry import tool
from .descriptors import Route


@tool
class SearchMCPDebugLogsToolSpec(ToolSpec):
    """Search MCP server debug logs for troubleshooting (developer mode only).

    By default, only shows logs from the current project directory.
    Use all_projects=True to search across all projects on this machine.
    """

    # This is a special utility tool that doesn't use an AI model
    model_name = "utility"
    adapter_class = "LoggingAdapter"
    context_window = 0
    timeout = 30

    # Route everything to the adapter so kwargs reach LoggingAdapter.generate
    query: str = Route.adapter(description="Search query (SQL LIKE pattern)")

    level: Optional[str] = Route.adapter(
        default=None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"
    )

    since: str = Route.adapter(
        default="1h", description="Time range (e.g., '1h', '30m', '1d')"
    )

    instance_id: Optional[str] = Route.adapter(
        default=None, description="Filter by specific instance ID"
    )

    all_projects: bool = Route.adapter(
        default=False,
        description="Search logs from all projects (default: current project only)",
    )

    limit: int = Route.adapter(default=100, description="Maximum results to return")
