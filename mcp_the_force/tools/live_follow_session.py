"""live_follow_session tool specification.

Tails CLI agent session transcripts for monitoring.
"""

import os
from typing import Optional

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.live_follow_session import LiveFollowSessionService


@tool
class LiveFollowSession(ToolSpec):
    """Follow a CLI agent session and return recent transcript content."""

    model_name = "live_follow_session"
    description = (
        "Follow a CLI agent session and return recent transcript content. "
        "Useful for monitoring what a running CLI agent (Codex, Claude, Gemini) "
        "is doing or has done."
    )

    # Use local service
    service_cls = LiveFollowSessionService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 30  # Quick operation

    # Parameters
    session_id: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The Force session ID to follow. "
            "This is the same session_id used with work_with."
        )
    )

    lines: int = Route.prompt(  # type: ignore[assignment]
        description=("(Optional) Number of recent entries to return. " "Default: 50"),
        default=50,
    )


# Direct async function for convenience and testing
async def live_follow_session(
    session_id: str,
    lines: int = 50,
    project_dir: Optional[str] = None,
) -> str:
    """
    Follow a CLI agent session and return recent transcript content.

    This is a convenience function that can be called directly without
    going through the MCP tool infrastructure.

    Args:
        session_id: The Force session ID to follow
        lines: Number of recent entries to return (default: 50)
        project_dir: Optional project directory (defaults to cwd)

    Returns:
        Formatted transcript content or error message
    """
    if project_dir is None:
        project_dir = os.getcwd()

    service = LiveFollowSessionService(project_dir=project_dir)
    return await service.follow(session_id=session_id, lines=lines)
