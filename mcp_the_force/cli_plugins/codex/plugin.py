"""
Codex CLI Plugin Implementation.

Handles command building for OpenAI Codex CLI.
Output parsing is in parser.py.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import cli_plugin
from mcp_the_force.cli_plugins.codex.parser import CodexParser

logger = logging.getLogger(__name__)


@cli_plugin("codex")
class CodexPlugin:
    """
    CLI plugin for OpenAI Codex CLI.

    Command formats:
    - New session: codex exec --json --context <dir> "<task>"
    - Resume: codex exec resume <thread_id> --json "<task>"

    Output format: JSONL (see parser.py)
    Note: Codex uses thread_id, NOT session_id.
    """

    def __init__(self) -> None:
        self._parser = CodexParser()

    @property
    def executable(self) -> str:
        return "codex"

    def build_new_session_args(
        self,
        task: str,
        context_dirs: List[str],
        role: Optional[str] = None,
        cli_flags: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> List[str]:
        """Build args for a new Codex CLI session.

        Note: Codex CLI doesn't support --role or --context flags.
        Role is ignored; context must be provided via working directory.
        """
        # --skip-git-repo-check allows execution in non-git directories
        # --yolo skips permission prompts
        args = ["exec", "--json", "--skip-git-repo-check", "--yolo"]

        # Enable full environment variable inheritance
        # By default, Codex filters out vars containing KEY/SECRET/TOKEN
        # We need these for API keys and other credentials
        args.extend(
            [
                "-c",
                'shell_environment_policy.inherit="all"',
                "-c",
                "shell_environment_policy.ignore_default_excludes=true",
            ]
        )

        # Add reasoning effort configuration if specified
        # Codex supports: low, medium, high, xhigh
        if reasoning_effort and reasoning_effort != "medium":
            args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
            logger.info(f"[CODEX] Setting reasoning effort: {reasoning_effort}")

        # Note: Codex CLI doesn't support --context flag
        # Context is provided via working directory instead

        # Note: Codex CLI doesn't support --role flag
        # Role/system prompt is not configurable in Codex

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
        """Build args for resuming a Codex CLI session.

        Note: Codex uses 'exec resume' pattern, NOT --resume flag.
        """
        # --skip-git-repo-check allows execution in non-git directories
        # --yolo skips permission prompts
        args = [
            "exec",
            "resume",
            session_id,
            "--json",
            "--skip-git-repo-check",
            "--yolo",
        ]

        # Enable full environment variable inheritance
        # By default, Codex filters out vars containing KEY/SECRET/TOKEN
        # We need these for API keys and other credentials
        args.extend(
            [
                "-c",
                'shell_environment_policy.inherit="all"',
                "-c",
                "shell_environment_policy.ignore_default_excludes=true",
            ]
        )

        # Add reasoning effort configuration if specified
        # Codex supports: low, medium, high, xhigh
        if reasoning_effort and reasoning_effort != "medium":
            args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
            logger.info(f"[CODEX] Setting reasoning effort: {reasoning_effort}")

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
        """Codex uses CLI flags, not env vars, for reasoning effort."""
        return {}  # Codex handles reasoning via -c flag, not env vars

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """Parse Codex CLI output. Delegates to CodexParser."""
        return self._parser.parse(output)

    def locate_transcript(
        self,
        cli_session_id: Optional[str],
        project_dir: str,
    ) -> Optional[Path]:
        """
        Locate a Codex transcript file by thread_id.

        Codex stores transcripts in: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
        Each JSONL file contains a thread.started event with the thread_id.

        Args:
            cli_session_id: The Codex thread_id to search for
            project_dir: Not used for Codex (sessions are global)

        Returns:
            Path to the transcript file, or None if not found
        """
        if not cli_session_id:
            return None

        home = Path(os.environ.get("HOME", os.path.expanduser("~")))
        sessions_dir = home / ".codex" / "sessions"

        if not sessions_dir.exists():
            return None

        # Search recent days (last 7 days)
        today = datetime.now()
        for days_ago in range(7):
            date = today - timedelta(days=days_ago)
            day_dir = (
                sessions_dir
                / date.strftime("%Y")
                / date.strftime("%m")
                / date.strftime("%d")
            )

            if not day_dir.exists():
                continue

            # Search all JSONL files in this day's directory
            for jsonl_file in day_dir.glob("rollout-*.jsonl"):
                if self._transcript_contains_thread_id(jsonl_file, cli_session_id):
                    return jsonl_file

        return None

    def find_recent_transcript_by_project(
        self,
        project_dir: str,
    ) -> Optional[Path]:
        """
        Find the most recent transcript for a given project directory.

        Used for pending sessions where we don't have the thread_id yet.

        Args:
            project_dir: The project directory to match against session_meta.cwd

        Returns:
            Path to the most recent matching transcript, or None if not found
        """
        home = Path(os.environ.get("HOME", os.path.expanduser("~")))
        sessions_dir = home / ".codex" / "sessions"

        if not sessions_dir.exists():
            return None

        # Search today only (pending sessions are very recent)
        today = datetime.now()
        day_dir = (
            sessions_dir
            / today.strftime("%Y")
            / today.strftime("%m")
            / today.strftime("%d")
        )

        if not day_dir.exists():
            return None

        # Find all transcripts and sort by modification time (most recent first)
        transcripts = list(day_dir.glob("rollout-*.jsonl"))
        transcripts.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Check each transcript for matching project directory
        for jsonl_file in transcripts:
            if self._transcript_matches_project(jsonl_file, project_dir):
                return jsonl_file

        return None

    def find_transcript_by_session_id(
        self,
        session_id: str,
    ) -> Optional[Path]:
        """
        Find a transcript containing the given Force session_id marker.

        work_with injects [force_session_id: {session_id}] into the task,
        which appears in the transcript. This method searches recent transcripts
        for this marker.

        Args:
            session_id: The Force session_id to search for

        Returns:
            Path to the matching transcript, or None if not found
        """
        home = Path(os.environ.get("HOME", os.path.expanduser("~")))
        sessions_dir = home / ".codex" / "sessions"

        if not sessions_dir.exists():
            return None

        # Search today only (pending sessions are very recent)
        today = datetime.now()
        day_dir = (
            sessions_dir
            / today.strftime("%Y")
            / today.strftime("%m")
            / today.strftime("%d")
        )

        if not day_dir.exists():
            return None

        # The marker we're looking for
        marker = f"[force_session_id: {session_id}]"

        # Find all transcripts and sort by modification time (most recent first)
        transcripts = list(day_dir.glob("rollout-*.jsonl"))
        transcripts.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Check each transcript for the session_id marker
        for jsonl_file in transcripts:
            if self._transcript_contains_text(jsonl_file, marker):
                return jsonl_file

        return None

    def _transcript_contains_text(self, path: Path, text: str) -> bool:
        """Check if a transcript contains the given text anywhere."""
        try:
            with open(path, "r") as f:
                # Read first 50KB - the marker should be near the start
                content = f.read(50 * 1024)
                return text in content
        except (OSError, IOError):
            pass
        return False

    def _transcript_matches_project(self, path: Path, project_dir: str) -> bool:
        """Check if a transcript's cwd matches the given project directory."""
        try:
            with open(path, "r") as f:
                for i, line in enumerate(f):
                    if i > 5:  # session_meta is in first few lines
                        break
                    try:
                        data = json.loads(line)
                        if data.get("type") == "session_meta":
                            cwd = data.get("payload", {}).get("cwd", "")
                            if cwd == project_dir:
                                return True
                    except json.JSONDecodeError:
                        continue
        except (OSError, IOError):
            pass
        return False

    def _transcript_contains_thread_id(self, path: Path, thread_id: str) -> bool:
        """Check if a transcript file contains the given thread_id."""
        try:
            with open(path, "r") as f:
                # Only need to check first few lines for session ID
                for i, line in enumerate(f):
                    if i > 10:  # session ID appears very early
                        break
                    try:
                        data = json.loads(line)
                        # Check root-level thread_id (older format)
                        if data.get("thread_id") == thread_id:
                            return True
                        # Check thread.started event (older format)
                        if (
                            data.get("type") == "thread.started"
                            and data.get("thread_id") == thread_id
                        ):
                            return True
                        # Check session_meta event (current format)
                        if data.get("type") == "session_meta":
                            payload = data.get("payload", {})
                            if payload.get("id") == thread_id:
                                return True
                    except json.JSONDecodeError:
                        continue
        except (OSError, IOError):
            pass
        return False
