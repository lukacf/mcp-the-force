"""
Claude CLI Plugin Implementation.

Handles command building for Anthropic Claude Code CLI.
Output parsing is in parser.py.
"""

from typing import List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import cli_plugin
from mcp_the_force.cli_plugins.claude.parser import ClaudeParser


@cli_plugin("claude")
class ClaudePlugin:
    """
    CLI plugin for Anthropic Claude Code CLI.

    Command formats:
    - New session: claude --print --add-dir <dir> -p "<task>"
    - Resume: claude --print --resume <session_id> -p "<task>"

    Output format: JSON array with events (see parser.py)
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
    ) -> List[str]:
        """Build args for a new Claude CLI session."""
        args = ["--print"]

        # Add context directories
        for dir_path in context_dirs:
            args.extend(["--add-dir", dir_path])

        # Add role if specified
        if role:
            args.extend(["--system-prompt", role])

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task with -p flag (required by Claude CLI)
        args.extend(["-p", task])

        return args

    def build_resume_args(
        self,
        session_id: str,
        task: str,
        cli_flags: Optional[str] = None,
    ) -> List[str]:
        """Build args for resuming a Claude CLI session."""
        args = ["--print", "--resume", session_id]

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task with -p flag (required by Claude CLI)
        args.extend(["-p", task])

        return args

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """Parse Claude CLI output. Delegates to ClaudeParser."""
        return self._parser.parse(output)
