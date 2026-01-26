"""
CLI Plugins Package.

Provides self-contained plugin implementations for different CLI tools (Claude, Gemini, Codex).
Each plugin knows how to:
- Build commands for new sessions
- Build commands for resuming sessions
- Parse output from the CLI

Uses @cli_plugin decorator for registration, similar to @tool pattern.
"""

from mcp_the_force.cli_plugins.base import CLIPlugin, ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import (
    CLI_PLUGIN_REGISTRY,
    cli_plugin,
    get_cli_plugin,
    list_cli_plugins,
)

# Import plugins to trigger registration via @cli_plugin decorator
from mcp_the_force.cli_plugins import claude as _claude  # noqa: F401
from mcp_the_force.cli_plugins import gemini as _gemini  # noqa: F401
from mcp_the_force.cli_plugins import codex as _codex  # noqa: F401

__all__ = [
    "CLIPlugin",
    "ParsedCLIResponse",
    "CLI_PLUGIN_REGISTRY",
    "cli_plugin",
    "get_cli_plugin",
    "list_cli_plugins",
]
