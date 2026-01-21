"""
LiveFollowSession: Service for tailing CLI agent session transcripts.

Provides functionality to follow CLI agent sessions in real-time,
showing recent transcript content.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from mcp_the_force.cli_agents.session_bridge import SessionBridge
from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer
from mcp_the_force.cli_plugins.registry import get_cli_plugin, list_cli_plugins

logger = logging.getLogger(__name__)


class LiveFollowSessionService:
    """
    Service for following CLI agent session transcripts.

    Locates and tails transcripts from different CLI agents (Codex, Claude, Gemini)
    using their respective storage locations.
    """

    def __init__(
        self,
        project_dir: str,
        session_bridge: Optional[SessionBridge] = None,
    ):
        """
        Initialize the service.

        Args:
            project_dir: The project directory (used for transcript location)
            session_bridge: Optional SessionBridge instance (for testing)
        """
        self._project_dir = project_dir
        # Use basename for DB lookups (consistent with CLIAgentService)
        self._project_name = os.path.basename(project_dir) if project_dir else "default"
        self._session_bridge = session_bridge or SessionBridge()

    async def execute(
        self,
        session_id: str,
        lines: int = 50,
        **_kwargs,
    ) -> str:
        """
        Execute the live follow session (tool executor entry point).

        Delegates to follow() for the actual implementation.
        """
        return await self.follow(session_id=session_id, lines=lines)

    async def follow(
        self,
        session_id: str,
        lines: int = 50,
    ) -> str:
        """
        Follow a CLI session and return recent transcript content.

        Supports both Force session IDs (looked up via bridge) and
        direct CLI session IDs (used directly with plugins).

        Args:
            session_id: Force session ID or CLI session ID to follow
            lines: Number of recent entries to return

        Returns:
            Formatted transcript content or error message
        """
        # Strategy 1: Try bridge lookup (Force session_id -> cli_session_id)
        transcript_path = await self._find_via_bridge(session_id)

        # Strategy 2: Check if session is pending (started but not completed)
        if not transcript_path:
            transcript_path = await self._find_pending_session(session_id)

        # Strategy 3: Try session_id directly as cli_session_id with each plugin
        if not transcript_path:
            transcript_path = self._find_via_direct_lookup(session_id)

        if not transcript_path:
            return f"Error: No transcript found for session '{session_id}'"

        # Tail the transcript
        return self._tail_transcript(transcript_path, session_id, lines)

    async def _find_via_bridge(self, session_id: str) -> Optional[Path]:
        """Try to find transcript via session bridge lookup."""
        cli_name = await self._get_cli_name(session_id)
        if not cli_name:
            return None

        cli_session_id = await self._session_bridge.get_cli_session_id(
            project=self._project_name,
            session_id=session_id,
            cli_name=cli_name,
        )
        # Skip pending sessions (handled by _find_pending_session)
        if not cli_session_id or cli_session_id == "__PENDING__":
            return None

        plugin = get_cli_plugin(cli_name)
        if not plugin:
            return None

        path = plugin.locate_transcript(
            cli_session_id=cli_session_id,
            project_dir=self._project_dir,
        )
        return path if path and path.exists() else None

    async def _find_pending_session(self, session_id: str) -> Optional[Path]:
        """Find transcript for a pending session by searching for session_id marker."""
        # Try with project_name first, then fallback to "." for compatibility
        is_pending, cli_name = await self._session_bridge.is_session_pending(
            project=self._project_name,
            session_id=session_id,
        )
        if not is_pending:
            # Fallback: try with "." (some contexts store with basename ".")
            is_pending, cli_name = await self._session_bridge.is_session_pending(
                project=".",
                session_id=session_id,
            )
        if not is_pending or not cli_name:
            return None

        plugin = get_cli_plugin(cli_name)
        if not plugin:
            return None

        # Search recent transcripts for the session_id marker
        # work_with injects [force_session_id: {session_id}] into the task
        if hasattr(plugin, "find_transcript_by_session_id"):
            path: Optional[Path] = plugin.find_transcript_by_session_id(session_id)
            if path and path.exists():
                logger.info(f"Found pending session transcript: {path}")
                return path

        return None

    def _find_via_direct_lookup(self, session_id: str) -> Optional[Path]:
        """Try session_id directly as cli_session_id with each plugin."""
        for cli_name in list_cli_plugins():
            plugin = get_cli_plugin(cli_name)
            if not plugin:
                continue

            path = plugin.locate_transcript(
                cli_session_id=session_id,
                project_dir=self._project_dir,
            )
            if path and path.exists():
                logger.debug(f"Found transcript via direct lookup with {cli_name}")
                return path

        return None

    def _tail_transcript(
        self, transcript_path: Path, session_id: str, lines: int
    ) -> str:
        """Tail a transcript file and return formatted content."""
        try:
            tailer = TranscriptTailer.from_file(transcript_path)
            content = tailer.tail_formatted(transcript_path, lines=lines)
            if not content:
                return f"No content in transcript for session '{session_id}'"
            return content
        except Exception as e:
            logger.error(f"Error reading transcript: {e}")
            return f"Error reading transcript: {e}"

    async def _get_cli_name(self, session_id: str) -> Optional[str]:
        """Get the CLI name for a session."""
        return await self._session_bridge.get_cli_name(
            project=self._project_name,
            session_id=session_id,
        )
