"""
Base CLI Plugin Protocol and Types.

Defines the interface that all CLI plugins must implement,
plus shared types like ParsedCLIResponse.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ParsedCLIResponse:
    """
    Unified response type from all CLI parsers.

    Normalizes differences between CLI output formats into a common structure.
    """

    session_id: Optional[str]
    """CLI-native session identifier (session_id for Claude/Gemini, thread_id for Codex)"""

    content: str
    """Extracted response content"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Optional metadata from the CLI output"""


class CLIPlugin(Protocol):
    """
    Protocol for CLI plugins that handle command building and output parsing.

    Each CLI (Claude, Gemini, Codex) has its own plugin implementation
    in a dedicated subfolder (e.g., cli_plugins/claude/).
    """

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

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """
        Parse CLI output into a structured response.

        Args:
            output: Raw CLI output (JSON, JSONL, etc.)

        Returns:
            ParsedCLIResponse with session_id and content
        """
        ...
