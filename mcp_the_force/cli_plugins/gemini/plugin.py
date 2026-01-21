"""
Gemini CLI Plugin Implementation.

Handles command building for Google Gemini CLI.
Output parsing is in parser.py.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import cli_plugin
from mcp_the_force.cli_plugins.gemini.parser import GeminiParser

logger = logging.getLogger(__name__)

# Track if we've warned about reasoning effort not being supported
_reasoning_warning_shown = False


@cli_plugin("gemini")
class GeminiPlugin:
    """
    CLI plugin for Google Gemini CLI.

    Command formats:
    - New session: gemini --output-format json --include-directories <dir> "<task>"
    - Resume: gemini --resume <session_id> --output-format json "<task>"

    Output format: JSON object (see parser.py)

    Note: Gemini CLI doesn't support reasoning effort configuration yet.
    The API supports thinking_level (low/high), but the CLI doesn't expose it.
    See: https://github.com/google-gemini/gemini-cli/issues/6693
    """

    def __init__(self) -> None:
        self._parser = GeminiParser()

    @property
    def executable(self) -> str:
        return "gemini"

    def build_new_session_args(
        self,
        task: str,
        context_dirs: List[str],
        role: Optional[str] = None,
        cli_flags: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> List[str]:
        """Build args for a new Gemini CLI session.

        Note: reasoning_effort is ignored - Gemini CLI doesn't support it yet.
        """
        self._warn_reasoning_not_supported(reasoning_effort)
        args = ["--output-format", "json", "--yolo"]

        # Add context directories
        for dir_path in context_dirs:
            args.extend(["--include-directories", dir_path])

        # Gemini CLI doesn't support --system-instruction, prepend role to task
        if role:
            task = f"Role: {role}\n\n{task}"

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task goes last
        args.append(task)

        return args

    def build_resume_args(
        self,
        session_id: str,
        task: str,
        cli_flags: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> List[str]:
        """Build args for resuming a Gemini CLI session.

        Note: reasoning_effort is ignored - Gemini CLI doesn't support it yet.
        """
        self._warn_reasoning_not_supported(reasoning_effort)
        args = ["--resume", session_id, "--output-format", "json", "--yolo"]

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task goes last
        args.append(task)

        return args

    def get_reasoning_env_vars(
        self,
        reasoning_effort: Optional[str] = None,
    ) -> Dict[str, str]:
        """Gemini CLI doesn't support reasoning effort via env vars."""
        return {}  # Not supported

    def _warn_reasoning_not_supported(self, reasoning_effort: Optional[str]) -> None:
        """Log a warning if reasoning_effort is set but not 'medium'."""
        global _reasoning_warning_shown
        if (
            reasoning_effort
            and reasoning_effort != "medium"
            and not _reasoning_warning_shown
        ):
            logger.warning(
                f"[GEMINI] reasoning_effort='{reasoning_effort}' ignored - "
                "Gemini CLI doesn't support this parameter yet. "
                "See: https://github.com/google-gemini/gemini-cli/issues/6693"
            )
            _reasoning_warning_shown = True

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """Parse Gemini CLI output. Delegates to GeminiParser."""
        return self._parser.parse(output)

    def locate_transcript(
        self,
        cli_session_id: Optional[str],
        project_dir: str,
    ) -> Optional[Path]:
        """
        Locate a Gemini CLI transcript file.

        Gemini CLI stores transcripts in: ~/.gemini/tmp/<project-hash>/
        The project hash is a SHA256 of the project directory path.
        Session files are in the chats/ subdirectory or as checkpoint-tag-*.json.

        Args:
            cli_session_id: Optional session tag (from /chat save <tag>)
            project_dir: The project directory (used to compute hash)

        Returns:
            Path to the transcript file, or None if not found
        """
        home = Path(os.environ.get("HOME", os.path.expanduser("~")))
        gemini_dir = home / ".gemini" / "tmp"

        if not gemini_dir.exists():
            return None

        # Compute project hash
        project_hash = self._compute_project_hash(project_dir)
        project_sessions_dir = gemini_dir / project_hash

        if not project_sessions_dir.exists():
            return None

        # If we have a session/tag ID, look for checkpoint-tag-{tag}.json
        if cli_session_id:
            tagged_file = project_sessions_dir / f"checkpoint-tag-{cli_session_id}.json"
            if tagged_file.exists():
                return tagged_file

        # Look in chats/ subdirectory for latest chat
        chats_dir = project_sessions_dir / "chats"
        if chats_dir.exists():
            chat_files = list(chats_dir.glob("*.json"))
            if chat_files:
                # Sort by modification time, newest first
                chat_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return chat_files[0]

        # Fallback: look for any JSON file in the project directory
        json_files = list(project_sessions_dir.glob("*.json"))
        if json_files:
            # Prefer checkpoint files
            checkpoint_files = [f for f in json_files if "checkpoint" in f.name]
            if checkpoint_files:
                checkpoint_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return checkpoint_files[0]
            # Otherwise, most recent JSON
            json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return json_files[0]

        return None

    def _compute_project_hash(self, project_dir: str) -> str:
        """
        Compute Gemini's project hash from a directory path.

        Gemini CLI uses SHA256 hash of the project path.
        """
        normalized = os.path.normpath(project_dir)
        return hashlib.sha256(normalized.encode()).hexdigest()
