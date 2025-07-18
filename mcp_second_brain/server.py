#!/usr/bin/env python3
"""MCP Second-Brain Server with dataclass-based tools."""

import logging
from .logging.setup import setup_logging

# Initialize the new logging system first
setup_logging()

# Also ensure operation_manager is available for Claude Code abort handling
from .operation_manager import operation_manager  # noqa: F401, E402

# Patch cancellation handler to prevent double responses
# This is THE fix for the double response issue when operations are cancelled
from . import patch_cancellation_handler  # noqa: F401, E402

# NOW import FastMCP after patches are applied
from fastmcp import FastMCP  # noqa: E402

# Import all tool definitions to register them
from .tools import definitions  # noqa: F401, E402 # This import triggers the @tool decorators
from .tools import search_memory  # noqa: F401, E402 # Import search_project_memory tool
from .tools.integration import (  # noqa: E402
    register_all_tools,
    create_list_models_tool,
    create_count_project_tokens_tool,
)

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("mcp-second-brain")

# Register all dataclass-based tools
logger.info("Registering dataclass-based tools...")
register_all_tools(mcp)

# Register utility tools
create_list_models_tool(mcp)
create_count_project_tokens_tool(mcp)
# Note: create_vector_store_tool is intentionally not registered to hide it from MCP clients

logger.info("MCP Second-Brain server initialized with dataclass-based tools")


def main():
    """Main entry point."""
    import asyncio
    import sys
    import signal
    import errno
    import selectors
    from typing import Iterator
    from .utils.docker_manager import docker_manager

    def _iter_leaves(exc: BaseException) -> Iterator[BaseException]:
        """Depth-first walk that yields every non-group exception."""
        if sys.version_info >= (3, 11) and type(exc).__name__ == "ExceptionGroup":
            for child in exc.exceptions:
                yield from _iter_leaves(child)
        else:
            yield exc

    # DISABLED: Testing if custom selector is causing race conditions
    # # macOS-specific workaround for KqueueSelector stdio hang bug
    # # See: https://github.com/python/cpython/issues/104344
    # # BUT: SelectSelector has a 1024 file descriptor limit that causes hangs
    # # with many concurrent file operations (e.g., vector store uploads).
    # # Using PollSelector instead which has no FD limit while still avoiding
    # # the KqueueSelector stdio issues.
    # if sys.platform == "darwin":

    #     class PollSelectorPolicy(asyncio.DefaultEventLoopPolicy):
    #         def new_event_loop(self):
    #             # poll(2) has no FD_SETSIZE limit unlike select(2)
    #             selector = selectors.PollSelector()
    #             return asyncio.SelectorEventLoop(selector)

    #     asyncio.set_event_loop_policy(PollSelectorPolicy())
    #     logger.info(
    #         "Using PollSelector on macOS to avoid both KqueueSelector stdio hangs "
    #         "and SelectSelector's 1024 FD limit"
    #     )
    
    logger.warning("Custom PollSelector DISABLED - using default event loop selector")

    # Ignore SIGPIPE to prevent crashes on broken pipes (Unix only)
    if sys.platform != "win32":
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    # Handle --help and --version
    if "--help" in sys.argv or "-h" in sys.argv:
        print("MCP Second-Brain Server")
        print("\nUsage: mcp-second-brain")
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

            print(version("mcp_second_brain"))
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
        logger.info("Installed custom event loop exception handler")
    
    # No loop for stdio transport - run once and exit on disconnection
    # Claude spawns a new server process for each session
    try:
        logger.info("Starting MCP server (stdio transport)...")

        # DISABLED: Docker manager may be causing event loop issues
        # Skip Docker initialization to test if it's the cause of hangs
        logger.warning("Docker service initialization DISABLED for debugging")
        
        # Clear any existing event loop so FastMCP can create its own
        asyncio.set_event_loop(None)
        
        # Register cleanup handlers for state reset
        from .utils.state_reset import state_reset_manager
        from .adapters.openai.client import OpenAIClientFactory
        
        # Register singletons to be cleared
        if hasattr(OpenAIClientFactory, '_instances'):
            state_reset_manager.register_singleton(OpenAIClientFactory._instances)
        
        logger.info("State reset manager configured for aggressive cleanup between queries")
        
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
            # Debug log all leaves for analysis
            import os
            from datetime import datetime

            try:
                debug_file = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")
                with open(debug_file, "a") as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    f.write(f"[{timestamp}] SERVER MAIN: Caught ExceptionGroup\n")
                    # Log all leaf exceptions
                    for i, leaf in enumerate(_iter_leaves(e)):
                        f.write(
                            f"[{timestamp}] EXG-leaf-{i}: {type(leaf).__name__}: {leaf}\n"
                        )
                        f.write(f"[{timestamp}] EXG-leaf-{i}-repr: {repr(leaf)}\n")
                        f.write(f"[{timestamp}] EXG-leaf-{i}-str: {str(leaf)}\n")
                    f.flush()
            except Exception:
                pass

            # Define what constitutes a benign disconnect error
            import anyio
            import fastmcp

            def is_benign(exc: BaseException) -> bool:
                """Check if exception is benign and should be suppressed."""
                # Check type name as string to handle import/namespace issues
                exc_type_name = type(exc).__name__
                exc_module = type(exc).__module__ or ""

                return (
                    isinstance(
                        exc,
                        (
                            asyncio.CancelledError,
                            BrokenPipeError,
                            ConnectionError,
                            EOFError,
                        ),
                    )
                    or exc_type_name
                    in ["BrokenResourceError", "ClosedResourceError", "EndOfStream"]
                    or "anyio" in exc_module
                    and exc_type_name
                    in ["BrokenResourceError", "ClosedResourceError", "EndOfStream"]
                    or (isinstance(exc, OSError) and exc.errno == errno.EPIPE)
                    or (
                        isinstance(exc, ValueError)
                        and "closed file" in str(exc).lower()
                    )
                    or (
                        isinstance(exc, RuntimeError)
                        and (
                            "stdout" in str(exc).lower() or "stdin" in str(exc).lower()
                        )
                    )
                    or (
                        hasattr(fastmcp, "exceptions")
                        and hasattr(fastmcp.exceptions, "ToolError")
                        and isinstance(exc, fastmcp.exceptions.ToolError)
                        and "cancelled" in str(exc).lower()
                    )
                    or (
                        isinstance(exc, AssertionError)
                        and "request already responded to" in str(exc).lower()
                    )
                )

            # Check if ALL leaves are benign
            leaves = list(_iter_leaves(e))
            benign_checks = [(leaf, is_benign(leaf)) for leaf in leaves]

            # Debug log the benign check results
            try:
                with open(debug_file, "a") as f:
                    for leaf, is_b in benign_checks:
                        f.write(
                            f"[{timestamp}] Benign check: {type(leaf).__name__} -> {is_b}\n"
                        )
                        if not is_b:
                            f.write(
                                f"[{timestamp}] Not benign because: isinstance checks failed\n"
                            )
                            f.write(
                                f"[{timestamp}] anyio.BrokenResourceError type: {anyio.BrokenResourceError}\n"
                            )
                            f.write(f"[{timestamp}] leaf type: {type(leaf)}\n")
                            f.write(
                                f"[{timestamp}] isinstance check: {isinstance(leaf, anyio.BrokenResourceError)}\n"
                            )
            except Exception:
                pass

            # Debug log the all() result
            all_benign = all(is_b for _, is_b in benign_checks)
            try:
                with open(debug_file, "a") as f:
                    f.write(f"[{timestamp}] All benign result: {all_benign}\n")
                    f.write(f"[{timestamp}] Benign checks list: {benign_checks}\n")
            except Exception:
                pass

            if all_benign:
                try:
                    with open(debug_file, "a") as f:
                        f.write(f"[{timestamp}] About to suppress and return\n")
                except Exception:
                    pass
                logger.info(
                    "Suppressed ExceptionGroup containing only benign disconnect errors"
                )
                # For stdio transport, this is expected behavior
                return  # Exit gracefully
            else:
                # Some real error remains – re-raise so we crash loudly
                logger.error(
                    "Server crashed with ExceptionGroup containing real errors"
                )
                raise

        # Not an ExceptionGroup - continue with original handler
        # Debug log to file
        import os
        from datetime import datetime

        try:
            debug_file = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")
            with open(debug_file, "a") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                f.write(
                    f"[{timestamp}] SERVER MAIN: Caught exception: {type(e).__name__}: {e}\n"
                )
                f.flush()
        except Exception:
            pass

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
