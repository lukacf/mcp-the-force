"""List sessions tool."""

from typing import Optional
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.list_sessions import ListSessionsService


@tool
class ListSessions(ToolSpec):
    """List existing sessions for the current project."""

    model_name = "list_sessions"
    description = (
        "List existing AI conversation sessions for the current project. "
        "Returns session IDs and tool names, ordered by most recent first."
    )

    # This is a local service, not an AI model
    service_cls = ListSessionsService
    adapter_class = None
    timeout = 30

    limit: int = Route.adapter(  # type: ignore[assignment]
        default=5,
        description=(
            "(Optional) Maximum number of sessions to return. "
            "Syntax: An integer. "
            "Default: 5. "
            "Example: limit=10"
        ),
    )

    search: Optional[str] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description=(
            "(Optional) Substring search filter for session_id or tool_name. "
            "Case-insensitive partial matching. "
            "Syntax: A string. "
            "Default: None (no filtering). "
            "Example: search='gpt52'"
        ),
    )

    include_summary: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description=(
            "(Optional) Whether to include cached summaries in the results. "
            "Only available for sessions that have been summarized. "
            "Syntax: A boolean (true or false). "
            "Default: false. "
            "Example: include_summary=true"
        ),
    )
