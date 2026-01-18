"""
SessionBridge: Maps Force session_id to CLI-native session identifiers.

Stores mappings in SQLite for persistence across process restarts.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionMapping:
    """A mapping from Force session to CLI session."""

    project: str
    session_id: str
    cli_name: str
    cli_session_id: str


class SessionBridge:
    """
    Manages session ID mappings between Force and CLI agents.

    Different CLIs use different session concepts:
    - Claude: session_id in JSON output
    - Gemini: session_id in JSON output
    - Codex: thread_id (NOT session_id) in JSONL output
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize SessionBridge with optional custom database path."""
        self._db_path = db_path

    async def store_cli_session_id(
        self,
        project: str,
        session_id: str,
        cli_name: str,
        cli_session_id: str,
    ) -> None:
        """
        Store a CLI session ID mapping.

        Args:
            project: Project identifier
            session_id: Force session ID
            cli_name: CLI name (claude, gemini, codex)
            cli_session_id: Native CLI session ID
        """
        raise NotImplementedError("SessionBridge.store_cli_session_id not implemented")

    async def get_cli_session_id(
        self,
        project: str,
        session_id: str,
        cli_name: str,
    ) -> Optional[str]:
        """
        Retrieve a CLI session ID for the given Force session.

        Args:
            project: Project identifier
            session_id: Force session ID
            cli_name: CLI name (claude, gemini, codex)

        Returns:
            The CLI session ID if found, None otherwise.
        """
        raise NotImplementedError("SessionBridge.get_cli_session_id not implemented")
