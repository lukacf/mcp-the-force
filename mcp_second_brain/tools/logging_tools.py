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
    query: str = Route.adapter("Search query (SQL LIKE pattern)")

    level: Optional[str] = Route.adapter(
        "Filter by log level (DEBUG, INFO, WARNING, ERROR)", default=None
    )

    since: str = Route.adapter(
        "Time range (e.g., '1h', '30m', '1d')", default="1h"
    )

    instance_id: Optional[str] = Route.adapter(
        "Filter by specific instance ID", default=None
    )

    all_projects: bool = Route.adapter(
        "Search logs from all projects (default: current project only)",
        default=False,
    )

    limit: int = Route.adapter("Maximum results to return", default=100)
