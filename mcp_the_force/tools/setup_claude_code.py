"""Setup Claude Code integration tool."""

from .base import ToolSpec
from .registry import tool
from ..local_services.setup_claude_code import SetupClaudeCodeService


@tool
class SetupClaudeCode(ToolSpec):
    """Install The Force agents into Claude Code."""

    model_name = "setup_claude_code"
    description = (
        "Install The Force agents into Claude Code's .claude/agents/ directory. "
        "This enables event-based parallel execution via the Task tool. "
        "After running, restart Claude Code to activate the agents. "
        "Agents installed: force-runner (dispatches tasks to AI models)."
    )

    # This is a local service, not an AI model
    service_cls = SetupClaudeCodeService
    adapter_class = None
    timeout = 30
