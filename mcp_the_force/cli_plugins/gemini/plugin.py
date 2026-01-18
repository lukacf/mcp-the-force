"""
Gemini CLI Plugin Implementation.

Handles command building for Google Gemini CLI.
Output parsing is in parser.py.
"""

from typing import List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import cli_plugin
from mcp_the_force.cli_plugins.gemini.parser import GeminiParser


@cli_plugin("gemini")
class GeminiPlugin:
    """
    CLI plugin for Google Gemini CLI.

    Command formats:
    - New session: gemini --output-format json --context <dir> "<task>"
    - Resume: gemini --session <session_id> --output-format json "<task>"

    Output format: JSON object (see parser.py)
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
    ) -> List[str]:
        """Build args for a new Gemini CLI session."""
        args = ["--output-format", "json"]

        # Add context directories
        for dir_path in context_dirs:
            args.extend(["--context", dir_path])

        # Add role if specified
        if role:
            args.extend(["--system-instruction", role])

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
    ) -> List[str]:
        """Build args for resuming a Gemini CLI session."""
        args = ["--session", session_id, "--output-format", "json"]

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task goes last
        args.append(task)

        return args

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """Parse Gemini CLI output. Delegates to GeminiParser."""
        return self._parser.parse(output)
