"""
Codex CLI Plugin.

Self-contained plugin for OpenAI Codex CLI.
"""

from mcp_the_force.cli_plugins.codex.plugin import CodexPlugin
from mcp_the_force.cli_plugins.codex.parser import CodexParser

__all__ = ["CodexPlugin", "CodexParser"]
