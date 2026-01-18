"""
CLI Availability Checker: Verify CLI tools are installed.

Provides clear error messages with installation instructions.
"""

import logging
import shutil
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CLIInfo:
    """Information about a CLI tool."""

    name: str
    executable: str
    install_command: str
    documentation_url: str


# Known CLI tools and their installation info
CLI_REGISTRY: Dict[str, CLIInfo] = {
    "claude": CLIInfo(
        name="Claude Code",
        executable="claude",
        install_command="npm install -g @anthropic/claude-code",
        documentation_url="https://docs.anthropic.com/claude-code",
    ),
    "gemini": CLIInfo(
        name="Gemini CLI",
        executable="gemini",
        install_command="npm install -g @google/gemini-cli",
        documentation_url="https://ai.google.dev/gemini-api/docs/cli",
    ),
    "codex": CLIInfo(
        name="Codex CLI",
        executable="codex",
        install_command="npm install -g @openai/codex",
        documentation_url="https://platform.openai.com/docs/guides/codex",
    ),
}


class CLIAvailabilityChecker:
    """
    Checks if CLI tools are installed and provides helpful error messages.
    """

    def __init__(self):
        """Initialize the checker."""
        self._cache: Dict[str, bool] = {}

    def is_available(self, cli_name: str) -> bool:
        """
        Check if a CLI is available.

        Args:
            cli_name: Name of the CLI (claude, gemini, codex)

        Returns:
            True if the CLI is installed and accessible
        """
        if cli_name in self._cache:
            return self._cache[cli_name]

        cli_info = CLI_REGISTRY.get(cli_name)
        if not cli_info:
            logger.warning(f"Unknown CLI: {cli_name}")
            return False

        available = shutil.which(cli_info.executable) is not None
        self._cache[cli_name] = available

        if not available:
            logger.warning(f"CLI not available: {cli_name}")

        return available

    def get_install_instructions(self, cli_name: str) -> str:
        """
        Get installation instructions for a CLI.

        Args:
            cli_name: Name of the CLI

        Returns:
            Installation instructions string
        """
        cli_info = CLI_REGISTRY.get(cli_name)
        if not cli_info:
            return f"Unknown CLI: {cli_name}"

        return (
            f"{cli_info.name} is not installed.\n"
            f"Install with: {cli_info.install_command}\n"
            f"Documentation: {cli_info.documentation_url}"
        )

    def get_error_message(self, cli_name: str) -> str:
        """
        Get a user-friendly error message for a missing CLI.

        Args:
            cli_name: Name of the CLI

        Returns:
            Error message with installation instructions
        """
        cli_info = CLI_REGISTRY.get(cli_name)
        if not cli_info:
            return f"Unknown CLI: {cli_name}"

        return (
            f"Error: {cli_info.name} CLI is not installed or not in PATH.\n\n"
            f"To install:\n"
            f"  {cli_info.install_command}\n\n"
            f"For more information:\n"
            f"  {cli_info.documentation_url}"
        )

    def check_all(self) -> Dict[str, bool]:
        """
        Check availability of all known CLIs.

        Returns:
            Dict mapping CLI name to availability status
        """
        return {name: self.is_available(name) for name in CLI_REGISTRY}

    def log_startup_status(self) -> None:
        """Log the availability status of all CLIs at startup."""
        status = self.check_all()
        available = [name for name, ok in status.items() if ok]
        missing = [name for name, ok in status.items() if not ok]

        if available:
            logger.info(f"Available CLIs: {', '.join(available)}")
        if missing:
            logger.warning(f"Missing CLIs: {', '.join(missing)}")
            for name in missing:
                logger.info(
                    f"  To install {name}: {CLI_REGISTRY[name].install_command}"
                )


class CLINotAvailableError(Exception):
    """Raised when a required CLI is not available."""

    def __init__(self, cli_name: str, message: Optional[str] = None):
        self.cli_name = cli_name
        if message is None:
            checker = CLIAvailabilityChecker()
            message = checker.get_error_message(cli_name)
        super().__init__(message)
