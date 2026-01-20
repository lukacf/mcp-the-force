"""
Gemini CLI Plugin Implementation.

Handles command building for Google Gemini CLI.
Output parsing is in parser.py.
"""

import logging
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
