#!/usr/bin/env python3
"""MCP The-Force Server with dataclass-based tools."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from .logging.setup import setup_logging

# Platform-specific imports
if sys.platform != "win32":
    import fcntl

# Initialize the new logging system first
setup_logging()

# Also ensure operation_manager is available for Claude Code abort handling
from .operation_manager import operation_manager  # noqa: F401, E402

# Patch cancellation handler to prevent double responses
# This is THE fix for the double response issue when operations are cancelled
# from . import patch_cancellation_handler  # noqa: F401, E402  # No longer needed with mcp@d4e14a4

# NOW import FastMCP after patches are applied
from fastmcp import FastMCP  # noqa: E402

# Import all tool definitions to register them
from .tools import definitions  # noqa: F401, E402 # This import triggers the @tool decorators
from .tools import search_history  # noqa: F401, E402 # Import search_project_history tool
from .tools.integration import (  # noqa: E402
    register_all_tools,
)

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("mcp-the-force")

# Register all dataclass-based tools
logger.debug("Registering dataclass-based tools...")
# Force an INFO level message to test if logging is working
logger.info("TEST: MCP The-Force server starting up...")
register_all_tools(mcp)

# Note: create_vector_store_tool is intentionally not registered to hide it from MCP clients
# Note: count_project_tokens is now registered as a ToolSpec-based tool

logger.debug("MCP The-Force server initialized with dataclass-based tools")


# Background cleanup task
_cleanup_task = None
_cleanup_lock_file = None


async def _periodic_cleanup_task():
    """Periodically clean up expired vector stores."""
    from .config import get_settings
    from .vectorstores.manager import vector_store_manager

    settings = get_settings()
    interval = (
        getattr(settings.vector_stores, "cleanup_interval_seconds", 300)
        if hasattr(settings, "vector_stores")
        else 300
    )

    logger.info(f"Starting periodic vector store cleanup task (interval: {interval}s)")

    # Get lock file path
    db_path = getattr(settings, "session_db_path", ".mcp_sessions.sqlite3")
    lock_path = Path(db_path).parent / ".vscleanup.lock"

    while True:
        await asyncio.sleep(interval)

        # Try to acquire file lock (Unix only)
        lock_acquired = False
        lock_fd = None

        if sys.platform != "win32":
            # Unix/Linux/macOS - use file locking
            try:
                # Open lock file
                lock_fd = os.open(
                    str(lock_path), os.O_CREAT | os.O_WRONLY | os.O_NONBLOCK
                )
                try:
                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                except BlockingIOError:
                    logger.debug("Cleanup already running in another process, skipping")
                    continue
            except Exception as e:
                logger.error(f"Error acquiring cleanup lock: {e}")
                if lock_fd is not None:
                    os.close(lock_fd)
                continue
        else:
            # Windows - for now, just proceed without locking
            # In production, could use msvcrt.locking or other Windows-specific mechanism
            lock_acquired = True

        if lock_acquired:
            try:
                # Perform cleanup
                cleaned_count = await vector_store_manager.cleanup_expired()
                if cleaned_count > 0:
                    logger.info(
                        f"Periodic cleanup: cleaned {cleaned_count} vector stores"
                    )
            except Exception as e:
                logger.error(f"Error during periodic cleanup: {e}")
            finally:
                # Release lock on Unix
                if sys.platform != "win32" and lock_fd is not None:
                    try:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                        os.close(lock_fd)
                    except Exception:
                        pass


# def _start_cleanup_task():
#     """Start the background cleanup task if not already running."""
#     global _cleanup_task
#
#     # Only start if not already running
#     if _cleanup_task is None or _cleanup_task.done():
#         loop = asyncio.get_event_loop()
#         _cleanup_task = loop.create_task(_periodic_cleanup_task())
#         logger.debug("Started background vector store cleanup task")


def main():
    """Main entry point."""
    import signal
    import errno

    # Ignore SIGPIPE to prevent crashes on broken pipes (Unix only)
    if sys.platform != "win32":
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    # Handle --help and --version
    if "--help" in sys.argv or "-h" in sys.argv:
        print("MCP The-Force Server")
        print("\nUsage: mcp-the-force")
        print(
            "\nA Model Context Protocol server providing access to multiple AI models"
        )
        print("with intelligent context management for large codebases.")
        print("\nOptions:")
        print("  -h, --help     Show this help message and exit")
        print("  -V, --version  Show version and exit")
        sys.exit(0)

    if "--version" in sys.argv or "-V" in sys.argv:
        try:
            from importlib.metadata import version

            print(version("mcp_the_force"))
        except ImportError:
            print("0.3.2")  # Fallback version
        sys.exit(0)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Install custom exception handler to suppress benign disconnect errors
    def ignore_broken_pipe(loop, context):
        """Suppress benign disconnect errors from AnyIO TaskGroup diagnostics."""
        import anyio

        exc = context.get("exception")
        if isinstance(
            exc,
            (
                anyio.ClosedResourceError,
                anyio.BrokenResourceError,
                anyio.EndOfStream,
                BrokenPipeError,
                ConnectionResetError,
            ),
        ):
            logger.debug("Suppressed benign disconnect error: %s", exc)
            return  # swallow
        # Fallback to default handler
        loop.default_exception_handler(context)

    # Let FastMCP create and manage its own event loop
    # This avoids conflicts between our custom loop management and FastMCP's internal handling

    # Install exception handler on the default event loop policy
    def setup_exception_handler():
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(ignore_broken_pipe)
        logger.debug("Installed custom event loop exception handler")

    # No loop for stdio transport - run once and exit on disconnection
    # Claude spawns a new server process for each session
    try:
        logger.info("Starting MCP server (stdio transport)...")

        # Clear any existing event loop so FastMCP can create its own
        asyncio.set_event_loop(None)

        # Register cleanup handlers for state reset
        from .utils.state_reset import state_reset_manager
        from .adapters.openai.client import OpenAIClientFactory

        # Register singletons to be cleared
        if hasattr(OpenAIClientFactory, "_instances"):
            state_reset_manager.register_singleton(OpenAIClientFactory._instances)

        logger.info(
            "State reset manager configured for aggressive cleanup between queries"
        )

        # Add startup hook to start cleanup task when FastMCP is ready
        @mcp.on_startup
        async def on_startup():
            """Start background tasks after server is ready."""
            # Start cleanup task in the background
            asyncio.create_task(_periodic_cleanup_task())
            logger.info("Background cleanup task started")

        # Now let FastMCP handle everything
        mcp.run()  # Will create its own event loop
        logger.info("MCP server exited normally")

    except KeyboardInterrupt:
        logger.info("MCP server interrupted by user")
        return  # Let the server shutdown gracefully
    except (EOFError, BrokenPipeError, OSError) as e:
        # These are normal disconnection scenarios for stdio
        if isinstance(e, OSError) and e.errno == errno.EPIPE:
            logger.info("Detected broken pipe - client disconnected")
        else:
            logger.info(f"Client disconnected: {type(e).__name__}")
        return  # Let the server shutdown gracefully
    except Exception as e:
        # Special handling for Python 3.11+ ExceptionGroup
        if sys.version_info >= (3, 11) and isinstance(e, BaseExceptionGroup):
            # Check if all exceptions in the group are benign disconnect errors
            import anyio

            benign_types = (
                asyncio.CancelledError,
                BrokenPipeError,
                ConnectionError,
                EOFError,
                anyio.ClosedResourceError,
                anyio.BrokenResourceError,
                anyio.EndOfStream,
            )

            def all_benign(exc_group):
                """Check if all exceptions in group are benign disconnects."""
                for exc in exc_group.exceptions:
                    if isinstance(exc, BaseExceptionGroup):
                        if not all_benign(exc):
                            return False
                    elif not isinstance(exc, benign_types):
                        if isinstance(exc, OSError) and exc.errno == errno.EPIPE:
                            continue
                        return False
                return True

            if all_benign(e):
                logger.info(
                    "Suppressed ExceptionGroup containing only benign disconnect errors"
                )
                return  # Exit gracefully
            else:
                # Some real error remains – re-raise
                logger.error(
                    "Server crashed with ExceptionGroup containing real errors"
                )
                raise

        # Handle anyio disconnection errors
        import anyio

        anyio_disconnect_errors = (
            anyio.ClosedResourceError,
            anyio.BrokenResourceError,
            anyio.EndOfStream,
        )

        if isinstance(e, anyio_disconnect_errors):
            logger.info(f"Client disconnected ({type(e).__name__})")
            return  # Normal disconnection

        # Real error - log and re-raise
        logger.error(f"MCP server crashed: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
