"""
Claude CLI Plugin.

Self-contained plugin for Anthropic Claude Code CLI.
"""

from mcp_the_force.cli_plugins.claude.plugin import ClaudePlugin
from mcp_the_force.cli_plugins.claude.parser import ClaudeParser

__all__ = ["ClaudePlugin", "ClaudeParser"]
