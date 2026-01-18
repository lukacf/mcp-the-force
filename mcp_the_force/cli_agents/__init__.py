"""
CLI Agents package.

Provides subprocess orchestration for CLI-based AI agents (Claude, Gemini, Codex).
"""

from mcp_the_force.cli_agents.session_bridge import SessionBridge
from mcp_the_force.cli_agents.executor import CLIExecutor, CLIResult
from mcp_the_force.cli_agents.compactor import Compactor
from mcp_the_force.cli_agents.environment import CommandBuilder, EnvironmentBuilder
from mcp_the_force.cli_agents.summarizer import OutputSummarizer

__all__ = [
    "SessionBridge",
    "CLIExecutor",
    "CLIResult",
    "Compactor",
    "CommandBuilder",
    "EnvironmentBuilder",
    "OutputSummarizer",
]
