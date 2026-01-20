"""
Codex CLI Plugin Implementation.

Handles command building for OpenAI Codex CLI.
Output parsing is in parser.py.
"""

import logging
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
