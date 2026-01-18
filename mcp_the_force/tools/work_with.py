"""work_with tool specification.

Executes tasks via CLI agents (Claude, Gemini, Codex) with session management.
"""

from typing import List, Optional

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.cli_agent_service import CLIAgentService


@tool
class WorkWith(ToolSpec):
    """Execute a task using a CLI agent (Claude, Gemini, or Codex)."""

    model_name = "work_with"
    description = (
        "Execute a task using a CLI-based AI agent. Supports Claude, Gemini, and Codex. "
        "Provides session continuity via automatic resume, cross-tool context injection, "
        "and isolated execution environments."
    )

    # Use local service instead of adapter
    service_cls = CLIAgentService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 300  # 5 minute timeout for CLI execution

    # Parameters
    agent: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The CLI agent to use for the task. "
            "Options: 'claude', 'gemini', 'codex'. "
            "Each agent has different capabilities and context limits."
        )
    )

    task: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The task or prompt for the agent. "
            "Be specific about what you want the agent to accomplish."
        )
    )

    session_id: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) A unique identifier for the conversation session. "
            "Reuse the same session_id to continue a conversation with context. "
            "The agent will automatically resume from the previous state."
        )
    )

    role: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Optional) Role name for system prompt configuration. "
            "Default: 'default'"
        ),
        default="default",
    )

    context: Optional[List[str]] = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Optional) List of file or directory paths to include as context. "
            "Paths are passed to the CLI agent via --add-dir flags."
        ),
        default=None,
    )
