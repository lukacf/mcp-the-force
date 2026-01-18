"""
CLI Plugin Registry.

Central registry for CLI plugins. Maps CLI names to their implementations.
Uses @cli_plugin decorator for registration, similar to @tool pattern.
"""

from typing import Callable, Dict, List, Optional, Type, TypeVar

from mcp_the_force.cli_plugins.base import CLIPlugin

# Global registry of all CLI plugins
CLI_PLUGIN_REGISTRY: Dict[str, CLIPlugin] = {}

T = TypeVar("T")


def cli_plugin(name: str) -> Callable[[Type[T]], Type[T]]:
    """
    Decorator that registers a CLI plugin.

    Usage:
        @cli_plugin("codex")
        class CodexPlugin:
            name = "codex"
            executable = "codex"

            def build_new_session_args(self, task, context_dirs):
                return ["exec", "--json", task]

            def build_resume_args(self, session_id, task):
                return ["exec", "resume", session_id, "--json"]

    Similar to @tool decorator for tools.
    """

    def decorator(cls: Type[T]) -> Type[T]:
        # Create an instance and register it
        instance = cls()
        CLI_PLUGIN_REGISTRY[name] = instance  # type: ignore[assignment]
        return cls

    return decorator


def get_cli_plugin(cli_name: str) -> Optional[CLIPlugin]:
    """
    Get a CLI plugin by name.

    Args:
        cli_name: The CLI identifier (e.g., "claude", "gemini", "codex")

    Returns:
        The CLIPlugin implementation, or None if not found
    """
    return CLI_PLUGIN_REGISTRY.get(cli_name)


def list_cli_plugins() -> List[str]:
    """
    List all registered CLI plugin names.

    Returns:
        List of CLI plugin names
    """
    return list(CLI_PLUGIN_REGISTRY.keys())
