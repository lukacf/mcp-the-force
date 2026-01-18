"""
Base CLI Plugin Protocol.

Defines the interface that all CLI plugins must implement.
"""

from typing import List, Optional, Protocol


class CLIPlugin(Protocol):
    """Protocol for CLI plugins that handle command building and output parsing."""

    @property
    def executable(self) -> str:
        """The CLI executable name (e.g., 'claude', 'gemini', 'codex')."""
        ...

    def build_new_session_args(
        self,
        task: str,
        context_dirs: List[str],
        role: Optional[str] = None,
        cli_flags: Optional[str] = None,
    ) -> List[str]:
        """
        Build command arguments for starting a new CLI session.

        Args:
            task: The task prompt for the agent
            context_dirs: List of directories to add as context
            role: Optional role/persona for the agent
            cli_flags: Optional additional CLI flags

        Returns:
            List of command arguments (not including executable)
        """
        ...

    def build_resume_args(
        self,
        session_id: str,
        task: str,
        cli_flags: Optional[str] = None,
    ) -> List[str]:
        """
        Build command arguments for resuming an existing CLI session.

        Args:
            session_id: The CLI-specific session ID to resume
            task: The continuation prompt
            cli_flags: Optional additional CLI flags

        Returns:
            List of command arguments (not including executable)
        """
        ...
