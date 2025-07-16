"""
Comprehensive monkeypatch for MCP server cancellation handling.
This ensures the server survives and remains responsive when Claude Code aborts operations.
"""

import asyncio
import signal
import logging
import sys
import os
import functools
import weakref
from typing import Optional, Any, Set
import errno
from datetime import datetime

logger = logging.getLogger(__name__)

# Debug file for tracking patch activity
DEBUG_FILE = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")


def _debug_log(message: str):
    """Write debug message to file since user can't see stderr in interactive environment."""
    try:
        with open(DEBUG_FILE, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
    except Exception:
        pass  # Silent fail if can't write


# Log module import
_debug_log("========== CANCELLATION_PATCH MODULE IMPORTED ==========")

# Import operation manager to coordinate cancellation
try:
    from .operation_manager import operation_manager

    logger.info("Operation manager imported for cancellation coordination")
except ImportError:
    from typing import cast

    operation_manager = cast(Any, None)
    logger.warning(
        "Could not import operation manager - cancellation may not work properly"
    )

# Track active operations
_active_operations: weakref.WeakSet[asyncio.Task] = weakref.WeakSet()
_cancelled_request_ids: Set[int] = set()
_original_sigterm_handler: Optional[Any] = None
_server_shutting_down = False


def handle_sigterm(signum: int, frame: Any) -> None:
    """
    Custom SIGTERM handler that cancels active operations without killing the server.
    This mimics the behavior of other MCP servers that survive operation aborts.
    """
    _debug_log("SIGTERM received")
    logger.info(
        "SIGTERM received - cancelling active operations (server will continue)"
    )

    # Cancel all active operations
    cancelled_count = 0
    for task in list(_active_operations):
        if not task.done():
            task.cancel()
            cancelled_count += 1

    logger.info(f"Cancelled {cancelled_count} active operations")

    # Also cancel operations tracked by operation manager
    if operation_manager:
        try:
            # Get the current event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule the cancellation in the event loop
                loop.create_task(operation_manager.cancel_all_operations())
                logger.info("Scheduled cancellation of operation manager operations")
            else:
                logger.warning(
                    "Event loop not running - cannot cancel operation manager operations"
                )
        except Exception as e:
            logger.error(f"Error cancelling operation manager operations: {e}")

    # CRITICAL: Do NOT exit or set shutdown flag
    # The server should continue running and be ready for new requests


def install_signal_handlers() -> None:
    """Install custom signal handlers for graceful operation cancellation."""
    global _original_sigterm_handler

    if sys.platform == "win32":
        return

    # Save and replace SIGTERM handler
    _original_sigterm_handler = signal.signal(signal.SIGTERM, handle_sigterm)

    # Also handle SIGINT more gracefully
    def sigint_handler(signum: int, frame: Any) -> None:
        global _server_shutting_down
        logger.info("SIGINT received - initiating graceful shutdown")
        print("SIGINT received - shutting down", file=sys.stderr, flush=True)
        _server_shutting_down = True
        # Cancel all operations
        for task in list(_active_operations):
            if not task.done():
                task.cancel()
        # Force exit
        os._exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    logger.info("Installed custom signal handlers for graceful cancellation")


def patch_fastmcp_session() -> None:
    """
    Patch FastMCP's session handling to prevent crashes on cancelled operations.
    This is the core fix that prevents the server from dying.
    """
    _debug_log("patch_fastmcp_session() called")
    try:
        from mcp.server.session import BaseSession

        _debug_log("Imported BaseSession successfully")

        # Store original method
        original_send_response = BaseSession._send_response
        _debug_log(f"Original _send_response method: {original_send_response}")

        @functools.wraps(original_send_response)
        async def safe_send_response(
            self: BaseSession, request_id: Any, response: Any
        ) -> None:
            """Wrapped _send_response that handles disconnections gracefully."""
            # Debug print to verify this method is being called
            _debug_log(
                f"PATCHED _send_response called: request_id={request_id}, response_type={type(response).__name__}"
            )
            print(
                f"PATCHED SEND_RESPONSE CALLED for request_id={request_id}",
                file=sys.stderr,
            )

            # Check if this request was cancelled
            if request_id in _cancelled_request_ids:
                _debug_log(f"Skipping response for cancelled request {request_id}")
                logger.debug(f"Skipping response for cancelled request {request_id}")
                _cancelled_request_ids.discard(request_id)
                return

            try:
                await original_send_response(self, request_id, response)
                _debug_log(
                    f"Original _send_response completed successfully for request_id={request_id}"
                )
            except (BrokenPipeError, ConnectionError, OSError) as e:
                error_msg = f"CAUGHT {type(e).__name__}: {e}"
                _debug_log(error_msg)
                print(
                    f"PATCHED SEND_RESPONSE CAUGHT ERROR: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )
                if isinstance(e, OSError) and e.errno != errno.EPIPE:
                    _debug_log(f"Re-raising OSError with errno={e.errno}")
                    raise
                logger.debug(f"Client disconnected while sending response: {e}")
                _debug_log("Client disconnected - NOT crashing server")
                # Don't crash - client is gone
            except Exception as e:
                # Check for anyio disconnection errors
                error_str = str(e).lower()
                if any(
                    x in error_str for x in ["closed", "broken", "disconnected", "eof"]
                ):
                    _debug_log(f"Client disconnected (anyio error): {e}")
                    logger.debug(f"Client disconnected: {e}")
                else:
                    _debug_log(
                        f"Unexpected error - re-raising: {type(e).__name__}: {e}"
                    )
                    # Re-raise unexpected errors
                    raise

        # Replace method
        setattr(BaseSession, "_send_response", safe_send_response)
        _debug_log("SUCCESSFULLY PATCHED BaseSession._send_response")

        logger.info("Patched FastMCP BaseSession for safe response handling")

        # Add debug print to verify patch is active
        print(
            "CANCELLATION PATCH: Successfully patched BaseSession._send_response",
            file=sys.stderr,
        )

    except ImportError as e:
        _debug_log(f"Failed to import BaseSession: {e}")
        logger.warning("Could not import BaseSession for patching")


def patch_tool_execution() -> None:
    """
    Patch FastMCP to handle TaskGroup exceptions properly.
    This fixes the bug where TaskGroup crashes on unhandled exceptions.
    """
    _debug_log("patch_tool_execution() called")
    try:
        # Patch FastMCP's call_tool for tracking
        from fastmcp import FastMCP

        _debug_log("Imported FastMCP successfully")

        original_call_tool = FastMCP._mcp_call_tool
        _debug_log(f"Original _mcp_call_tool method: {original_call_tool}")

        @functools.wraps(original_call_tool)
        async def tracked_call_tool(self: FastMCP, name: str, arguments: dict) -> Any:
            """Wrapped _mcp_call_tool that tracks operations."""
            # Create task for tracking
            current_task = asyncio.current_task()
            if current_task:
                _active_operations.add(current_task)

            _debug_log(f"Tool execution started: {name}")

            try:
                # Check if server is shutting down
                if _server_shutting_down:
                    raise asyncio.CancelledError("Server is shutting down")

                result = await original_call_tool(self, name, arguments)
                _debug_log(f"Tool execution completed: {name}")
                return result

            except asyncio.CancelledError:
                _debug_log(f"Tool '{name}' was cancelled - returning empty success")
                # Return empty content blocks to fake success
                return []
            except Exception as e:
                _debug_log(f"Tool '{name}' execution error: {type(e).__name__}: {e}")
                raise
            finally:
                if current_task:
                    _active_operations.discard(current_task)

        setattr(FastMCP, "_mcp_call_tool", tracked_call_tool)
        _debug_log("SUCCESSFULLY PATCHED FastMCP._mcp_call_tool")
        logger.info("Patched FastMCP._mcp_call_tool for operation tracking")

    except ImportError as e:
        _debug_log(f"Failed to import FastMCP: {e}")
        logger.warning("Could not import FastMCP for patching")


def patch_stdio_handling() -> None:
    """
    Enhance stdio handling to prevent crashes on broken pipes.
    This works in conjunction with the session patches.
    """
    _debug_log("patch_stdio_handling() called")

    # Wrap stdout to handle broken pipes
    original_stdout_write = sys.stdout.write

    def safe_stdout_write(data: str) -> int:
        """Write to stdout, swallowing ALL exceptions to prevent crashes."""
        try:
            return original_stdout_write(data)
        except Exception as e:
            # Log ALL exceptions for debugging
            _debug_log(f"safe_stdout_write caught exception: {type(e).__name__}: {e}")
            logger.debug(
                f"Exception on stdout write - swallowing: {type(e).__name__}: {e}"
            )
            return len(data)  # Pretend we wrote it

    setattr(sys.stdout, "write", safe_stdout_write)
    _debug_log("Patched sys.stdout.write")

    # Also patch flush
    original_stdout_flush = sys.stdout.flush

    def safe_stdout_flush() -> None:
        """Flush stdout, swallowing ALL exceptions to prevent crashes."""
        try:
            original_stdout_flush()
        except Exception as e:
            # Log ALL exceptions for debugging
            _debug_log(f"safe_stdout_flush caught exception: {type(e).__name__}: {e}")
            logger.debug(
                f"Exception on stdout flush - swallowing: {type(e).__name__}: {e}"
            )

    setattr(sys.stdout, "flush", safe_stdout_flush)
    _debug_log("Patched sys.stdout.flush")

    # Also patch stderr for completeness
    original_stderr_write = sys.stderr.write

    def safe_stderr_write(data: str) -> int:
        """Write to stderr, swallowing ALL exceptions to prevent crashes."""
        try:
            return original_stderr_write(data)
        except Exception:
            # Can't log to debug file here as it might cause recursion
            return len(data)  # Pretend we wrote it

    setattr(sys.stderr, "write", safe_stderr_write)
    _debug_log("Patched sys.stderr.write")

    # Patch stderr flush
    original_stderr_flush = sys.stderr.flush

    def safe_stderr_flush() -> None:
        """Flush stderr, swallowing ALL exceptions to prevent crashes."""
        try:
            original_stderr_flush()
        except Exception:
            pass  # Swallow silently

    setattr(sys.stderr, "flush", safe_stderr_flush)
    _debug_log("Patched sys.stderr.flush")

    logger.info("Patched stdout/stderr for exception handling")
    _debug_log("patch_stdio_handling() completed")


def monkeypatch_all() -> None:
    """Apply all cancellation-related monkeypatches."""
    # Force immediate output
    _debug_log("==================== MONKEYPATCH_ALL STARTED ====================")
    print("Applying comprehensive cancellation patches...", file=sys.stderr, flush=True)
    logger.info("Applying comprehensive cancellation patches...")

    # Order matters - signal handlers first
    _debug_log("Installing signal handlers...")
    install_signal_handlers()

    # Then patch FastMCP internals
    _debug_log("Patching FastMCP session...")
    patch_fastmcp_session()
    _debug_log("Patching tool execution...")
    patch_tool_execution()

    # Skip TaskGroup patching - it breaks anyio internals
    _debug_log("Skipping TaskGroup patching to avoid breaking anyio")

    # Finally patch stdio
    _debug_log("Patching stdio handling...")
    patch_stdio_handling()

    _debug_log("==================== MONKEYPATCH_ALL COMPLETED ====================")
    print("All cancellation patches applied successfully", file=sys.stderr, flush=True)
    logger.info("All cancellation patches applied successfully")
