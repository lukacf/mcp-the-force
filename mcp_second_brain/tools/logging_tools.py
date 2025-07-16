"""MCP tools for searching debug logs."""

from typing import Any

from .base import ToolSpec
from .registry import tool
from .descriptors import Route


@tool
class SearchMCPDebugLogs(ToolSpec):
    """Search MCP server debug logs for troubleshooting (developer mode only).

    All parameters are optional. Omitted parameters widen the search.

    Examples:
    - Recent warnings in current project: severity="warning", since="30m"
    - Find text across all projects: text="CallToolRequest", project="all"
    - E2E test errors: severity="error", context="e2e"
    - Specific instance logs: instance="mcp-second-brain_dev_8747aa1d"
    - Oldest to newest: since="24h", order="asc"
    """

    # This is a special utility tool that doesn't use an AI model
    model_name = "utility"
    adapter_class = "LoggingAdapter"
    context_window = 0
    timeout = 30

    # Route everything to the adapter so kwargs reach LoggingAdapter.generate
    text: Any = Route.adapter(
        default=None,
        description="Search for this text in log messages (case-insensitive substring)",
    )

    severity: Any = Route.adapter(
        default=None,
        description="Log level filter: debug|info|warning|error|critical (single or list)",
    )

    since: Any = Route.adapter(
        default="1h",
        description="Start time - relative (5m, 2h, 3d) or absolute (2025-07-16T12:30:00Z)",
    )

    until: Any = Route.adapter(
        default="now", description="End time - relative or absolute timestamp"
    )

    project: Any = Route.adapter(
        default="current",
        description="Project filter: 'current' (default), 'all', or specific path",
    )

    context: Any = Route.adapter(
        default="*",
        description="Environment filter from instance_id: dev|test|e2e|* (all)",
    )

    instance: Any = Route.adapter(
        default="*",
        description="Instance ID filter - exact or wildcard pattern (e.g. '*_dev_*')",
    )

    limit: Any = Route.adapter(default=100, description="Maximum results (1-1000)")

    order: Any = Route.adapter(
        default="desc",
        description="Sort order: 'desc' (newest first) or 'asc' (oldest first)",
    )
