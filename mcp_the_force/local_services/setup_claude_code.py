"""Service to set up Claude Code integration with The Force agents."""

from pathlib import Path
from typing import Dict, Any

from ..config import get_project_dir

# Agent template for force-runner
FORCE_RUNNER_AGENT = """---
name: force-runner
description: Run AI model tasks in background via The Force. Use when user wants parallel work with GPT-5.2, Gemini, Codex, Claude, Grok, etc. Spawns CLI agents that can read files, run commands, and work autonomously.
tools:
  - mcp__the-force__work_with
---
You are The Force runner - dispatch tasks to AI models via `work_with`.

**Tool:**
- `work_with(agent, task, session_id)` - Spawn CLI agent that can read files, run commands, work autonomously

**Models:**
- `gpt-5.2`, `gpt-5.2-pro`, `gpt-4.1` - OpenAI
- `gemini-3-pro-preview`, `gemini-3-flash-preview` - Google
- `claude-sonnet-4-5`, `claude-opus-4-5` - Anthropic

**Rules:**
1. Always use `work_with` - it spawns an agentic CLI with file/command access
2. Always provide descriptive `session_id` for conversation continuity
3. Pick the right model for the task
"""

# Map of agent name to template
AGENTS = {
    "force-runner": FORCE_RUNNER_AGENT,
}


class SetupClaudeCodeService:
    """Service to install The Force agents into Claude Code."""

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Install The Force agents into .claude/agents/ directory.

        Returns:
            Dict with agents_installed, agents_dir, and message.
        """
        project_dir = get_project_dir()
        agents_dir = Path(project_dir) / ".claude" / "agents"

        # Create agents directory if it doesn't exist
        agents_dir.mkdir(parents=True, exist_ok=True)

        # Install each agent
        installed = []
        for agent_name, agent_template in AGENTS.items():
            agent_file = agents_dir / f"{agent_name}.md"
            agent_file.write_text(agent_template)
            installed.append(agent_name)

        return {
            "agents_installed": installed,
            "agents_dir": str(agents_dir),
            "message": "Agents installed successfully. Please restart Claude Code to activate them.",
        }
