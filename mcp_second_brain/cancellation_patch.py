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

logger = logging.getLogger(__name__)

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
    try:
        from mcp.server.session import BaseSession

        # Store original method
        original_send_response = BaseSession._send_response

        @functools.wraps(original_send_response)
        async def safe_send_response(
            self: BaseSession, request_id: Any, response: Any
        ) -> None:
            """Wrapped _send_response that handles disconnections gracefully."""
            # Check if this request was cancelled
            if request_id in _cancelled_request_ids:
                logger.debug(f"Skipping response for cancelled request {request_id}")
                _cancelled_request_ids.discard(request_id)
                return

            try:
                await original_send_response(self, request_id, response)
            except (BrokenPipeError, ConnectionError, OSError) as e:
                if isinstance(e, OSError) and e.errno != errno.EPIPE:
                    raise
                logger.debug(f"Client disconnected while sending response: {e}")
                # Don't crash - client is gone
            except Exception as e:
                # Check for anyio disconnection errors
                error_str = str(e).lower()
                if any(
                    x in error_str for x in ["closed", "broken", "disconnected", "eof"]
                ):
                    logger.debug(f"Client disconnected: {e}")
                else:
                    # Re-raise unexpected errors
                    raise

        # Replace method
        setattr(BaseSession, "_send_response", safe_send_response)

        logger.info("Patched FastMCP BaseSession for safe response handling")

    except ImportError:
        logger.warning("Could not import BaseSession for patching")


def patch_tool_execution() -> None:
    """
    Wrap tool execution to track operations and handle cancellation properly.
    """
    try:
        from mcp.server.fastmcp import FastMCP

        original_call_tool = FastMCP.call_tool

        @functools.wraps(original_call_tool)
        async def tracked_call_tool(self: FastMCP, name: str, arguments: dict) -> Any:
            """Wrapped call_tool that tracks operations for cancellation."""
            # Create task for tracking
            current_task = asyncio.current_task()
            if current_task:
                _active_operations.add(current_task)

            try:
                # Check if server is shutting down
                if _server_shutting_down:
                    raise asyncio.CancelledError("Server is shutting down")

                result = await original_call_tool(self, name, arguments)
                return result

            except asyncio.CancelledError:
                logger.info(f"Tool '{name}' execution cancelled")
                # Mark the request as cancelled to prevent response
                # This is a simplified approach - in production you'd track request IDs properly
                raise
            finally:
                if current_task:
                    _active_operations.discard(current_task)

        setattr(FastMCP, "call_tool", tracked_call_tool)
        logger.info("Patched FastMCP.call_tool for operation tracking")

    except ImportError:
        logger.warning("Could not import FastMCP for patching")


def patch_stdio_handling() -> None:
    """
    Enhance stdio handling to prevent crashes on broken pipes.
    This works in conjunction with the session patches.
    """
    # Wrap stdout to handle broken pipes
    original_stdout_write = sys.stdout.write

    def safe_stdout_write(data: str) -> int:
        """Write to stdout, ignoring broken pipe errors."""
        try:
            return original_stdout_write(data)
        except (BrokenPipeError, OSError) as e:
            if isinstance(e, OSError) and e.errno != errno.EPIPE:
                raise
            logger.debug("Broken pipe on stdout - client disconnected")
            return len(data)  # Pretend we wrote it

    setattr(sys.stdout, "write", safe_stdout_write)

    # Also patch flush
    original_stdout_flush = sys.stdout.flush

    def safe_stdout_flush() -> None:
        """Flush stdout, ignoring broken pipe errors."""
        try:
            original_stdout_flush()
        except (BrokenPipeError, OSError) as e:
            if isinstance(e, OSError) and e.errno != errno.EPIPE:
                raise
            logger.debug("Broken pipe on stdout flush - client disconnected")

    setattr(sys.stdout, "flush", safe_stdout_flush)

    logger.info("Patched stdout for broken pipe handling")


def monkeypatch_all() -> None:
    """Apply all cancellation-related monkeypatches."""
    # Force immediate output
    print("Applying comprehensive cancellation patches...", file=sys.stderr, flush=True)
    logger.info("Applying comprehensive cancellation patches...")

    # Order matters - signal handlers first
    install_signal_handlers()

    # Then patch FastMCP internals
    patch_fastmcp_session()
    patch_tool_execution()

    # Finally patch stdio
    patch_stdio_handling()

    print("All cancellation patches applied successfully", file=sys.stderr, flush=True)
    logger.info("All cancellation patches applied successfully")
