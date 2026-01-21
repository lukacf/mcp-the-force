"""
Claude CLI Plugin Implementation.

Handles command building for Anthropic Claude Code CLI.
Output parsing is in parser.py.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import cli_plugin
from mcp_the_force.cli_plugins.claude.parser import ClaudeParser

logger = logging.getLogger(__name__)

# Mapping from reasoning effort levels to MAX_THINKING_TOKENS values
# Based on Claude Code's default of 31,999 tokens
REASONING_EFFORT_TO_TOKENS: Dict[str, int] = {
    "low": 16_000,
    "medium": 31_999,  # Claude Code default
    "high": 63_999,  # 2x default
    "xhigh": 127_999,  # 4x default (may not be fully utilized)
}


@cli_plugin("claude")
class ClaudePlugin:
    """
    CLI plugin for Anthropic Claude Code CLI.

    Command formats:
    - New session: claude --print --add-dir <dir> "<task>"
    - Resume: claude --print --resume <session_id> "<task>"

    Output format: JSON array with events (see parser.py)

    Reasoning effort is controlled via MAX_THINKING_TOKENS environment variable.
    """

    def __init__(self) -> None:
        self._parser = ClaudeParser()

    @property
    def executable(self) -> str:
        return "claude"

    def build_new_session_args(
        self,
        task: str,
        context_dirs: List[str],
        role: Optional[str] = None,
        cli_flags: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> List[str]:
        """Build args for a new Claude CLI session.

        Note: reasoning_effort is handled via MAX_THINKING_TOKENS env var,
        not CLI flags. See get_reasoning_env_vars().
        """
        _ = reasoning_effort  # Handled via env var, not CLI flag
        args = ["--print", "--output-format", "json", "--dangerously-skip-permissions"]

        # Add context directories
        for dir_path in context_dirs:
            args.extend(["--add-dir", dir_path])

        # Add role if specified
        if role:
            args.extend(["--system-prompt", role])

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task as positional argument
        args.append(task)

        return args

    def build_resume_args(
        self,
        session_id: str,
        task: str,
        cli_flags: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> List[str]:
        """Build args for resuming a Claude CLI session.

        Note: reasoning_effort is handled via MAX_THINKING_TOKENS env var,
        not CLI flags. See get_reasoning_env_vars().
        """
        _ = reasoning_effort  # Handled via env var, not CLI flag
        args = [
            "--print",
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "--resume",
            session_id,
        ]

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task as positional argument
        args.append(task)

        return args

    def get_reasoning_env_vars(
        self,
        reasoning_effort: Optional[str] = None,
    ) -> Dict[str, str]:
        """Get environment variables for reasoning effort.

        Claude Code uses MAX_THINKING_TOKENS to control thinking budget.
        Only set if different from default (medium).
        """
        if not reasoning_effort or reasoning_effort == "medium":
            return {}  # Use Claude's default

        tokens = REASONING_EFFORT_TO_TOKENS.get(reasoning_effort)
        if tokens is None:
            logger.warning(
                f"[CLAUDE] Unknown reasoning effort '{reasoning_effort}', using default"
            )
            return {}

        logger.info(
            f"[CLAUDE] Setting MAX_THINKING_TOKENS={tokens} for {reasoning_effort}"
        )
        return {"MAX_THINKING_TOKENS": str(tokens)}

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """Parse Claude CLI output. Delegates to ClaudeParser."""
        return self._parser.parse(output)

    def locate_transcript(
        self,
        cli_session_id: Optional[str],
        project_dir: str,
    ) -> Optional[Path]:
        """
        Locate a Claude Code transcript file.

        Claude Code stores transcripts in: ~/.claude/projects/<path-hash>/<session>.jsonl
        The path hash is the project directory path with / replaced by -.

        Args:
            cli_session_id: The Claude session ID (used as filename)
            project_dir: The project directory (used to compute path hash)

        Returns:
            Path to the transcript file, or None if not found
        """
        home = Path(os.environ.get("HOME", os.path.expanduser("~")))
        projects_dir = home / ".claude" / "projects"

        if not projects_dir.exists():
            return None

        # Compute project hash from directory path
        project_hash = self._compute_project_hash(project_dir)
        project_sessions_dir = projects_dir / project_hash

        if not project_sessions_dir.exists():
            return None

        # If we have a session ID, look for that specific file
        if cli_session_id:
            # Try exact match first
            session_file = project_sessions_dir / f"{cli_session_id}.jsonl"
            if session_file.exists():
                return session_file

            # Try with agent- prefix
            agent_file = project_sessions_dir / f"agent-{cli_session_id}.jsonl"
            if agent_file.exists():
                return agent_file

            # Try without extension
            for jsonl_file in project_sessions_dir.glob("*.jsonl"):
                if cli_session_id in jsonl_file.stem:
                    return jsonl_file

        # If no session ID or not found, return the most recent file
        jsonl_files = list(project_sessions_dir.glob("*.jsonl"))
        if jsonl_files:
            # Sort by modification time, newest first
            jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return jsonl_files[0]

        return None

    def _compute_project_hash(self, project_dir: str) -> str:
        """
        Compute Claude's project hash from a directory path.

        Claude Code uses the path with / replaced by - as the folder name.
        e.g., /Users/luka/src/raik -> -Users-luka-src-raik
        """
        # Normalize the path
        normalized = os.path.normpath(project_dir)
        # Replace / with - (and handle leading /)
        return normalized.replace("/", "-")
