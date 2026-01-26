"""
Gemini CLI Plugin.

Self-contained plugin for Google Gemini CLI.
"""

from mcp_the_force.cli_plugins.gemini.plugin import GeminiPlugin
from mcp_the_force.cli_plugins.gemini.parser import GeminiParser

__all__ = ["GeminiPlugin", "GeminiParser"]
