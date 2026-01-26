"""
CLI Agents package.

Provides subprocess orchestration for CLI-based AI agents (Claude, Gemini, Codex).
Command building and parsing is handled by CLI plugins in cli_plugins/*.
"""

from mcp_the_force.cli_agents.session_bridge import SessionBridge
from mcp_the_force.cli_agents.executor import CLIExecutor, CLIResult
from mcp_the_force.cli_agents.compactor import Compactor
from mcp_the_force.cli_agents.environment import EnvironmentBuilder
from mcp_the_force.cli_agents.summarizer import OutputSummarizer

__all__ = [
    "SessionBridge",
    "CLIExecutor",
    "CLIResult",
    "Compactor",
    "EnvironmentBuilder",
    "OutputSummarizer",
]
