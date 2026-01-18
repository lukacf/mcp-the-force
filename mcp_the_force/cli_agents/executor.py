"""
CLIExecutor: Subprocess management for CLI agent execution.

Handles spawning, environment isolation, output capture, and timeout.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CLIResult:
    """Result from a CLI execution."""

    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False


class CLIExecutor:
    """
    Executes CLI agents as subprocesses.

    Provides:
    - Environment variable injection (HOME isolation)
    - stdout/stderr capture
    - Timeout handling with process termination
    """

    async def execute(
        self,
        command: List[str],
        env: Dict[str, str],
        timeout: int,
        cwd: Optional[str] = None,
    ) -> CLIResult:
        """
        Execute a CLI command as a subprocess.

        Args:
            command: Command and arguments to execute
            env: Environment variables for the subprocess
            timeout: Maximum execution time in seconds
            cwd: Working directory (optional)

        Returns:
            CLIResult with stdout, stderr, return_code, and timed_out flag
        """
        raise NotImplementedError("CLIExecutor.execute not implemented")
