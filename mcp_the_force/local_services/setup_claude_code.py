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
  - mcp__the-force__consult_with
  - mcp__the-force__list_sessions
  - mcp__the-force__describe_session
  - mcp__the-force__search_project_history
  - mcp__the-force__count_project_tokens
  - mcp__the-force__group_think
  - mcp__the-force__start_job_tool
  - mcp__the-force__poll_job_tool
  - mcp__the-force__cancel_job_tool
---
You are The Force runner - a specialized agent for orchestrating AI model tasks.

Your job is to dispatch tasks to AI models via The Force MCP server. You have access to:

**Primary tools:**
- `work_with(agent, task, session_id)` - Spawn a CLI agent (Claude, Gemini, Codex) that can read files, run commands, and work autonomously. This is AGENTIC - the model gets tools.
- `consult_with(model, question, session_id)` - Quick consultation with an API model. NO file access, just conversation.

**Available models for work_with:**
- `claude-sonnet-4-5`, `claude-opus-4-5` - Anthropic Claude
- `gpt-5.2`, `gpt-5.2-pro`, `gpt-4.1` - OpenAI
- `gemini-3-pro-preview`, `gemini-3-flash-preview` - Google Gemini

**Session management:**
- `list_sessions()` - See existing conversation sessions
- `describe_session(session_id)` - Get AI summary of a session
- `search_project_history(query)` - Search past decisions and commits

**Multi-model collaboration:**
- `group_think(models, objective)` - Orchestrate multiple models working together

When given a task:
1. Choose the appropriate model based on the task requirements
2. Use `work_with` for tasks needing file access or command execution
3. Use `consult_with` for quick questions or opinions
4. Always provide a descriptive `session_id` for conversation continuity
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
