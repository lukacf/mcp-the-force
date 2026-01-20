"""work_with tool specification.

Executes tasks via CLI agents (Claude, Gemini, Codex) with session management.
"""

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.cli_agent_service import CLIAgentService


def _generate_agent_description() -> str:
    """Generate agent parameter description from blueprint registry."""
    from ..cli_agents.model_cli_resolver import get_all_cli_models
    from .registry import list_tools

    # Ensure blueprints are loaded
    list_tools()

    cli_models = get_all_cli_models()
    if not cli_models:
        return (
            "(Required) The model to use for the task. "
            "Use any model registered with CLI support."
        )

    # Group by CLI type
    by_cli: dict[str, list[str]] = {}
    for model_name, cli_name in sorted(cli_models.items()):
        by_cli.setdefault(cli_name, []).append(model_name)

    # Build description
    parts = [
        "(Required) The model to use for the task. Available models with CLI support:"
    ]
    for cli_name in sorted(by_cli.keys()):
        models = by_cli[cli_name]
        parts.append(f"  {cli_name.upper()}: {', '.join(repr(m) for m in models)}")

    return " ".join(parts)


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
        description=_generate_agent_description()
    )

    task: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The task or prompt for the agent. "
            "Be specific about what you want the agent to accomplish. "
            "Note: The agent will automatically work from the current project directory."
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

    reasoning_effort: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Optional) Controls the depth of the agent's reasoning/thinking. "
            "Supported levels: 'low', 'medium', 'high', 'xhigh' (extra high). "
            "Higher effort = better quality but longer execution. "
            "Support varies by CLI: Codex supports all levels, Claude uses "
            "MAX_THINKING_TOKENS (low=16k, medium=32k, high=64k), Gemini "
            "doesn't support this parameter yet. "
            "Default: 'medium'"
        ),
        default="medium",
    )
