"""
Codex CLI Plugin Implementation.

Handles command building for OpenAI Codex CLI.
Output parsing is in parser.py.
"""

from typing import List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse
from mcp_the_force.cli_plugins.registry import cli_plugin
from mcp_the_force.cli_plugins.codex.parser import CodexParser


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
    ) -> List[str]:
        """Build args for a new Codex CLI session."""
        args = ["exec", "--json"]

        # Add context directories
        for dir_path in context_dirs:
            args.extend(["--context", dir_path])

        # Add role if specified
        if role:
            args.extend(["--role", role])

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
        """Build args for resuming a Codex CLI session.

        Note: Codex uses 'exec resume' pattern, NOT --resume flag.
        """
        args = ["exec", "resume", session_id, "--json"]

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task goes last
        args.append(task)

        return args

    def parse_output(self, output: str) -> ParsedCLIResponse:
        """Parse Codex CLI output. Delegates to CodexParser."""
        return self._parser.parse(output)
