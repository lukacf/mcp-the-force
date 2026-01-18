"""
CLI Plugin Implementations.

Concrete implementations of CLI plugins for Claude, Gemini, and Codex CLIs.
Uses @cli_plugin decorator for automatic registration.
"""

from typing import List, Optional

from mcp_the_force.cli_plugins.registry import cli_plugin


@cli_plugin("claude")
class ClaudePlugin:
    """CLI plugin for Anthropic Claude CLI."""

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
        """Build args for a new Claude CLI session.

        Format: claude --print --add-dir <dir> -p "<task>"
        """
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
        """Build args for resuming a Claude CLI session.

        Format: claude --print --resume <session_id> -p "<task>"
        """
        args = ["--print", "--resume", session_id]

        # Add any extra CLI flags
        if cli_flags:
            args.extend(cli_flags.split())

        # Task with -p flag (required by Claude CLI)
        args.extend(["-p", task])

        return args


@cli_plugin("gemini")
class GeminiPlugin:
    """CLI plugin for Google Gemini CLI."""

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


@cli_plugin("codex")
class CodexPlugin:
    """CLI plugin for OpenAI Codex CLI."""

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
