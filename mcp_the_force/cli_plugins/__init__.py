"""
CLI Plugins Package.

Provides plugin implementations for different CLI tools (Claude, Gemini, Codex).
Each plugin knows how to:
- Build commands for new sessions
- Build commands for resuming sessions
- Parse output from the CLI

Uses @cli_plugin decorator for registration, similar to @tool pattern.
"""

from mcp_the_force.cli_plugins.base import CLIPlugin
from mcp_the_force.cli_plugins.registry import (
    CLI_PLUGIN_REGISTRY,
    cli_plugin,
    get_cli_plugin,
    list_cli_plugins,
)

# Import plugins to trigger registration via @cli_plugin decorator
from mcp_the_force.cli_plugins import plugins as _plugins  # noqa: F401

__all__ = [
    "CLIPlugin",
    "CLI_PLUGIN_REGISTRY",
    "cli_plugin",
    "get_cli_plugin",
    "list_cli_plugins",
]
