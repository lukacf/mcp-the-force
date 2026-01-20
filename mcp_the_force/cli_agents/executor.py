"""
CLIExecutor: Subprocess management for CLI agent execution.

Handles spawning, environment isolation, output capture, and timeout.
Includes idle timeout to handle CLI processes that hang after completion.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum output capture size (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024

# Default idle timeout (10 minutes) - kills process if no output for this duration
# This works around Codex CLI hanging issues: https://github.com/openai/codex/issues/5773
DEFAULT_IDLE_TIMEOUT = 600


@dataclass
class CLIResult:
    """Result from a CLI execution."""

    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False
    idle_timeout: bool = False  # True if killed due to no output


class CLIExecutor:
    """
    Executes CLI agents as subprocesses.

    Provides:
    - Environment variable injection (HOME isolation)
    - stdout/stderr streaming capture
    - Total timeout handling with process termination
    - Idle timeout to detect hung processes (no output for N seconds)
    """

    def __init__(self, idle_timeout: int = DEFAULT_IDLE_TIMEOUT):
        """
        Initialize executor with idle timeout.

        Args:
            idle_timeout: Kill process if no output for this many seconds.
                         Default 600 (10 minutes) to handle xhigh reasoning.
        """
        self._idle_timeout = idle_timeout

    async def execute(
        self,
        command: List[str],
        env: Dict[str, str],
        timeout: int,
        cwd: Optional[str] = None,
        idle_timeout: Optional[int] = None,
    ) -> CLIResult:
        """
        Execute a CLI command as a subprocess with idle timeout detection.

        Args:
            command: Command and arguments to execute
            env: Environment variables for the subprocess
            timeout: Maximum total execution time in seconds
            cwd: Working directory (optional)
            idle_timeout: Override default idle timeout (optional)

        Returns:
            CLIResult with stdout, stderr, return_code, and timeout flags
        """
        logger.debug(f"Executing: {' '.join(command)}")
        logger.debug(
            f"CWD: {cwd}, timeout: {timeout}s, idle_timeout: {idle_timeout or self._idle_timeout}s"
        )

        effective_idle_timeout = (
            idle_timeout if idle_timeout is not None else self._idle_timeout
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,  # Don't inherit MCP's stdin
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            return await self._read_with_idle_timeout(
                process, timeout, effective_idle_timeout
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

    async def _read_with_idle_timeout(
        self,
        process: asyncio.subprocess.Process,
        total_timeout: int,
        idle_timeout: int,
    ) -> CLIResult:
        """
        Read process output with both total and idle timeout detection.

        Streams stdout/stderr and tracks when output was last received.
        Kills the process if:
        - Total timeout exceeded
        - No output received for idle_timeout seconds
        - MCP call is cancelled

        Args:
            process: The subprocess to read from
            total_timeout: Maximum total execution time
            idle_timeout: Maximum time to wait for new output

        Returns:
            CLIResult with captured output and status flags
        """
        stdout_chunks: List[bytes] = []
        stderr_chunks: List[bytes] = []
        stdout_size = 0
        stderr_size = 0

        start_time = time.monotonic()
        last_output_time = start_time

        async def read_stream(
            stream: Optional[asyncio.StreamReader],
            chunks: List[bytes],
            current_size: int,
        ) -> tuple[int, bool]:
            """Read available data from stream. Returns (new_size, got_data)."""
            nonlocal last_output_time

            if stream is None:
                return current_size, False

            try:
                # Non-blocking read with short timeout
                data = await asyncio.wait_for(stream.read(8192), timeout=0.1)
                if data:
                    last_output_time = time.monotonic()
                    if current_size < MAX_OUTPUT_SIZE:
                        chunks.append(data)
                        current_size += len(data)
                    return current_size, True
                return current_size, False
            except asyncio.TimeoutError:
                return current_size, False

        try:
            while True:
                # Check if process has exited
                if process.returncode is not None:
                    # Process exited, drain remaining output
                    if process.stdout:
                        remaining = await process.stdout.read()
                        if remaining and stdout_size < MAX_OUTPUT_SIZE:
                            stdout_chunks.append(remaining)
                    if process.stderr:
                        remaining = await process.stderr.read()
                        if remaining and stderr_size < MAX_OUTPUT_SIZE:
                            stderr_chunks.append(remaining)

                    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")[
                        :MAX_OUTPUT_SIZE
                    ]
                    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")[
                        :MAX_OUTPUT_SIZE
                    ]

                    return CLIResult(
                        stdout=stdout,
                        stderr=stderr,
                        return_code=process.returncode,
                        timed_out=False,
                    )

                # Read from both streams
                stdout_size, got_stdout = await read_stream(
                    process.stdout, stdout_chunks, stdout_size
                )
                stderr_size, got_stderr = await read_stream(
                    process.stderr, stderr_chunks, stderr_size
                )

                current_time = time.monotonic()
                elapsed = current_time - start_time
                idle_duration = current_time - last_output_time

                # Check total timeout
                if elapsed >= total_timeout:
                    logger.warning(
                        f"Total timeout ({total_timeout}s) exceeded, killing process"
                    )
                    process.kill()
                    await process.wait()

                    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")[
                        :MAX_OUTPUT_SIZE
                    ]
                    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")[
                        :MAX_OUTPUT_SIZE
                    ]

                    return CLIResult(
                        stdout=stdout,
                        stderr=stderr,
                        return_code=-1,
                        timed_out=True,
                    )

                # Check idle timeout (only after we've received some output)
                if stdout_chunks or stderr_chunks:
                    if idle_duration >= idle_timeout:
                        logger.warning(
                            f"Idle timeout ({idle_timeout}s) exceeded - no output for "
                            f"{idle_duration:.1f}s. Process may be hung. Killing."
                        )
                        process.kill()
                        await process.wait()

                        stdout = b"".join(stdout_chunks).decode(
                            "utf-8", errors="replace"
                        )[:MAX_OUTPUT_SIZE]
                        stderr = b"".join(stderr_chunks).decode(
                            "utf-8", errors="replace"
                        )[:MAX_OUTPUT_SIZE]

                        return CLIResult(
                            stdout=stdout,
                            stderr=stderr,
                            return_code=-1,
                            timed_out=False,
                            idle_timeout=True,
                        )

                # Small sleep to avoid busy-waiting
                if not got_stdout and not got_stderr:
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            # MCP call was aborted - kill the subprocess
            logger.warning("Execution cancelled, killing subprocess")
            process.kill()
            await process.wait()
            raise  # Re-raise to propagate cancellation
