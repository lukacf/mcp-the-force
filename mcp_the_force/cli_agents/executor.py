"""
CLIExecutor: Subprocess management for CLI agent execution.

Handles spawning, environment isolation, output capture, and timeout.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum output capture size (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024


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
        logger.debug(f"Executing: {' '.join(command)}")
        logger.debug(f"CWD: {cwd}, timeout: {timeout}s")

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,  # Don't inherit MCP's stdin
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                # Limit output size
                stdout = stdout_bytes.decode("utf-8", errors="replace")[
                    :MAX_OUTPUT_SIZE
                ]
                stderr = stderr_bytes.decode("utf-8", errors="replace")[
                    :MAX_OUTPUT_SIZE
                ]

                return CLIResult(
                    stdout=stdout,
                    stderr=stderr,
                    return_code=process.returncode or 0,
                    timed_out=False,
                )

            except asyncio.TimeoutError:
                logger.warning(f"Command timed out after {timeout}s, killing process")
                process.kill()
                await process.wait()

                # Capture any partial output
                stdout = ""
                stderr = ""
                if process.stdout:
                    try:
                        partial = await asyncio.wait_for(
                            process.stdout.read(MAX_OUTPUT_SIZE),
                            timeout=1,
                        )
                        stdout = partial.decode("utf-8", errors="replace")
                    except (asyncio.TimeoutError, Exception):
                        pass

                if process.stderr:
                    try:
                        partial = await asyncio.wait_for(
                            process.stderr.read(MAX_OUTPUT_SIZE),
                            timeout=1,
                        )
                        stderr = partial.decode("utf-8", errors="replace")
                    except (asyncio.TimeoutError, Exception):
                        pass

                return CLIResult(
                    stdout=stdout,
                    stderr=stderr,
                    return_code=-1,
                    timed_out=True,
                )

        except FileNotFoundError:
            # Could be command not found OR cwd not found
            if cwd and not Path(cwd).exists():
                logger.error(f"Working directory not found: {cwd}")
                return CLIResult(
                    stdout="",
                    stderr=f"Working directory not found: {cwd}",
                    return_code=127,
                    timed_out=False,
                )
            else:
                logger.error(f"Command not found: {command[0]}")
                return CLIResult(
                    stdout="",
                    stderr=f"Command not found: {command[0]}",
                    return_code=127,
                    timed_out=False,
                )
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return CLIResult(
                stdout="",
                stderr=str(e),
                return_code=-1,
                timed_out=False,
            )
